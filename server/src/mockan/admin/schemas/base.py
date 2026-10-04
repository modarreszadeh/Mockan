"""Base models: camelCase on the wire, snake_case in Python (arch §10)."""

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """Output models. Build them from ORM objects with `model_validate`."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


class CamelInput(CamelModel):
    """Input models reject unknown fields, so a typo can't be silently ignored."""

    model_config = ConfigDict(extra="forbid")
