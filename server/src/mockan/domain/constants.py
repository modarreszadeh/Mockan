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

# Admin API input limits. The Panel enforces the same or looser values (`panel/src/lib/checks.ts`).
MAX_DISPLAY_NAME_LENGTH = 100
MAX_ALLOWED_ORIGINS = 50
MAX_ORIGIN_LENGTH = 255

# Service catalog. A PathPrefix is one or more non-empty segments: `/limsa`, `/api/limsa`.
SERVICE_NAME_REGEX = re.compile(r"^[a-z][a-z0-9-]*$")
PATH_PREFIX_REGEX = re.compile(r"^(?:/[A-Za-z0-9._~-]+)+$")
MAX_SERVICE_NAME_LENGTH = 100
MAX_PATH_PREFIX_LENGTH = 200
MAX_BASE_URL_LENGTH = 2048
MIN_TIMEOUT_SECONDS = 1
MAX_TIMEOUT_SECONDS = 3600
DEFAULT_TIMEOUT_SECONDS = 100
MAX_EXTRA_HEADERS = 50
