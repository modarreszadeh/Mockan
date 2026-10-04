"""Validators shared by several schemas."""

import re

HEADER_NAME = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")


def no_nul(value: str) -> str:
    """PostgreSQL text and jsonb can't hold NUL; reject it here instead of failing on insert."""
    if "\0" in value:
        raise ValueError("Remove the NUL (\\u0000) character.")
    return value


def check_headers(
    headers: dict[str, str], limit: int, forbidden: frozenset[str] = frozenset()
) -> dict[str, str]:
    """Header names must be HTTP tokens and values must not contain line breaks or NUL."""
    if len(headers) > limit:
        raise ValueError(f"Use at most {limit} headers.")
    for name, content in headers.items():
        if HEADER_NAME.fullmatch(name) is None:
            raise ValueError(f"“{name}” isn't a valid header name.")
        if name.lower() in forbidden:
            raise ValueError(f"“{name}” is set by Mockan and can't be overridden.")
        if any(char in content for char in "\r\n\0"):
            raise ValueError(f"The value of “{name}” can't contain line breaks.")
    return headers
