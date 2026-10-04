"""Limits and fixed vocabularies. The Panel (`panel/src/lib/checks.ts`) uses the same values."""

import re

# DeveloperSlug (glossary, arch §2). Use `fullmatch`, never `match`.
SLUG_REGEX = re.compile(r"^[a-z][a-z0-9-]{1,31}$")
# Besides these, every slug starting with "_" is reserved (e.g. `_mockan`, arch §6.2).
RESERVED_SLUGS = frozenset({"api", "hubs", "health"})

HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")
ANY_METHOD = "ANY"

MAX_BODY_BYTES = 1_048_576
MAX_DELAY_MS = 30_000
MAX_REGEX_LENGTH = 512
MIN_STATUS = 100
MAX_STATUS = 599
DEFAULT_PRIORITY = 100
SAMPLE_BYTES = 16_384
