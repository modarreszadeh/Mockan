"""Developers: sign-in upsert (first login creates the Developer) and `PUT /me`."""

import uuid

from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mockan.admin.problems import DomainError, validation_error
from mockan.admin.schemas.developer import DeveloperUpdateIn
from mockan.admin.services.changes import diff
from mockan.domain.enums import AuditAction, AuditEntityType
from mockan.domain.errors import ErrorCode
from mockan.domain.validation import slug_problem
from mockan.infrastructure import audit
from mockan.infrastructure.db.errors import violated_constraint
from mockan.infrastructure.db.models import Developer
from mockan.infrastructure.settings import MockanSettings


async def get_by_id(session: AsyncSession, developer_id: uuid.UUID) -> Developer | None:
    return await session.get(Developer, developer_id)


async def _by_subject(session: AsyncSession, subject: str) -> Developer | None:
    return await session.scalar(select(Developer).where(Developer.sso_subject == subject))


async def _create(
    session: AsyncSession, settings: MockanSettings, subject: str, display_name: str, is_admin: bool
) -> Developer | None:
    """Insert the Developer; `None` when a parallel request created the same subject first."""
    developer = Developer(
        sso_subject=subject,
        display_name=display_name,
        allowed_origins=list(settings.default_allowed_origins),
        is_admin=is_admin,
    )
    session.add(developer)
    try:
        await session.flush()  # assigns the UUIDv7 the audit row refers to
        audit.record(
            session,
            developer,
            AuditAction.CREATE,
            AuditEntityType.DEVELOPER,
            developer.id,
            {"displayName": display_name, "isAdmin": is_admin},
        )
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        if violated_constraint(error) != "uq_developers_sso_subject":
            raise
        return None
    return developer


async def sign_in(
    session: AsyncSession,
    settings: MockanSettings,
    *,
    subject: str,
    display_name: str,
    grant_admin: bool = False,
) -> Developer:
    """Find the Developer for an SSO subject, creating it on first login.

    `is_admin` comes from `MOCKAN_ADMIN_SSO_SUBJECTS` (or `grant_admin`, dev mode only). It is
    applied on creation and as a promotion on later logins; a login never removes admin rights.
    """
    wants_admin = grant_admin or subject in settings.admin_sso_subjects
    developer = await _by_subject(session, subject)
    if developer is None:
        developer = await _create(session, settings, subject, display_name, wants_admin)
        if developer is None:
            developer = await _by_subject(session, subject)
        if developer is None:  # pragma: no cover - the unique violation proves the row exists
            raise RuntimeError(f"Developer {subject!r} vanished during sign-in.")
        return developer
    if wants_admin and not developer.is_admin:
        developer.is_admin = True
        audit.record(
            session,
            developer,
            AuditAction.UPDATE,
            AuditEntityType.DEVELOPER,
            developer.id,
            {"isAdmin": {"from": False, "to": True}},
        )
        await session.commit()
    return developer


async def update_profile(
    session: AsyncSession, developer: Developer, update: DeveloperUpdateIn
) -> Developer:
    """`PUT /me`: display name, allowed origins, and the slug (settable once)."""
    new_slug = update.slug if update.slug != developer.slug else None
    if new_slug is not None:
        if developer.slug is not None:
            raise DomainError(
                ErrorCode.SLUG_IMMUTABLE,
                409,
                "Your slug can't be changed",
                errors={"slug": ["Your workspace slug is already set and can't be changed."]},
            )
        if problem := slug_problem(new_slug):
            raise validation_error({"slug": [problem]})
        if await session.scalar(select(exists().where(Developer.slug == new_slug))):
            raise _slug_taken(new_slug)

    slug = new_slug or developer.slug
    display_name = update.display_name or developer.display_name
    allowed_origins = (
        update.allowed_origins if update.allowed_origins is not None else developer.allowed_origins
    )
    changes = diff(
        {
            "slug": developer.slug,
            "displayName": developer.display_name,
            "allowedOrigins": developer.allowed_origins,
        },
        {"slug": slug, "displayName": display_name, "allowedOrigins": allowed_origins},
    )
    if not changes:
        return developer

    developer.slug = slug
    developer.display_name = display_name
    developer.allowed_origins = allowed_origins
    audit.record(
        session, developer, AuditAction.UPDATE, AuditEntityType.DEVELOPER, developer.id, changes
    )
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        if violated_constraint(error) == "uq_developers_slug" and new_slug is not None:
            raise _slug_taken(new_slug) from error  # lost the race for the slug
        raise
    return developer


def _slug_taken(slug: str) -> DomainError:
    return DomainError(
        ErrorCode.SLUG_TAKEN,
        409,
        "Slug already in use",
        errors={"slug": [f"“{slug}” is already taken. Try another one."]},
    )
