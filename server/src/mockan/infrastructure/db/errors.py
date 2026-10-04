"""Helpers for reading PostgreSQL errors that SQLAlchemy wraps."""

from sqlalchemy.exc import IntegrityError


def violated_constraint(error: IntegrityError) -> str | None:
    """Name of the constraint an `IntegrityError` violated (e.g. `uq_developers_slug`).

    asyncpg exposes it as `constraint_name`; SQLAlchemy's adapter keeps the asyncpg exception as
    `__cause__` of `error.orig`.
    """
    original = error.orig
    for candidate in (original, getattr(original, "__cause__", None)):
        name = getattr(candidate, "constraint_name", None)
        if isinstance(name, str) and name:
            return name
    return None
