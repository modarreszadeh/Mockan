"""SQLAlchemy declarative base for schema `mockan` (tables arrive in B2, arch §8)."""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

SCHEMA = "mockan"

# Stable constraint names keep Alembic autogenerate diffs deterministic.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base class of every ORM model."""

    metadata = MetaData(schema=SCHEMA, naming_convention=NAMING_CONVENTION)
