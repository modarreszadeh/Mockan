#!/usr/bin/env bash
# deploy.sh: deploy Mockan from the images CI publishes to GHCR, and keep .env in shape.
#
# Usage (run from a checkout of this repository, in deploy/compose):
#   ./deploy.sh                  # deploy the `latest` images
#   ./deploy.sh abc1234          # deploy a specific git SHA (or branch) tag
#   ./deploy.sh --rollback       # redeploy the tag that was running before the last deploy
#   ./deploy.sh --dry-run        # validate .env and show the plan; changes nothing
#   ./deploy.sh --check-db       # show the database revision
#   ./deploy.sh --no-pull        # use the images already on this machine
#   IMAGE_TAG=abc1234 ./deploy.sh
#
# What it does with .env: creates it from .env.production.example when missing, generates the
# secrets that are empty (MOCKAN_SESSION_SECRET, and for the bundled database POSTGRES_PASSWORD and
# MOCKAN_DATABASE_URL) without printing them, and stops with a list of the required values you still
# have to fill (Keycloak, admin subjects, ...).
# Database: MOCKAN_DB_MODE=bundled (default) runs a PostgreSQL container next to the app;
# MOCKAN_DB_MODE=external uses a shared PostgreSQL reachable on a Docker network (MOCKAN_DB_NETWORK)
# at the MOCKAN_DATABASE_URL you put in .env.
# Updating compose files or nginx.conf is a `git pull` in this checkout; the images come from GHCR.
#
# Needs: Docker with Compose >= 2.24, openssl, curl (health check; skipped when missing).
# A rollback restores the images only. Database migrations are not reverted.

set -euo pipefail
cd "$(dirname "$0")"

COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"
ENV_FILE=".env"
ENV_TEMPLATE=".env.production.example"
TAG_FILE=".last-deployed-tag"      # the tag that was running before the current one

say()  { printf '▶ %s\n' "$*"; }
warn() { printf '⚠ %s\n' "$*" >&2; }
die()  { printf '✗ %s\n' "$*" >&2; exit 1; }

# ── Arguments ────────────────────────────────────────────────────────────────
NO_PULL=false; CHECK_DB=false; DRY_RUN=false; ROLLBACK=false; TAG_ARG=""
for arg in "$@"; do
  case "$arg" in
    --no-pull)  NO_PULL=true ;;
    --check-db) CHECK_DB=true ;;
    --dry-run)  DRY_RUN=true ;;
    --rollback) ROLLBACK=true ;;
    -h|--help)  sed -n '2,19p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    --*)        die "Unknown flag: $arg (see --help)" ;;
    *)          TAG_ARG="$arg" ;;
  esac
done

# ── .env helpers (never `source` the file: values may contain anything) ─────────
env_get() {  # env_get KEY -> value without surrounding quotes
  local line value
  line=$(grep -E "^$1=" "$ENV_FILE" 2>/dev/null | tail -n1 || true)
  value=${line#*=}
  case "$value" in
    \'*\') value=${value#\'}; value=${value%\'} ;;
    \"*\") value=${value#\"}; value=${value%\"} ;;
  esac
  printf '%s' "$value"
}

env_set() {  # env_set KEY VALUE: replace the line or append it (value never shown)
  local tmp
  tmp=$(mktemp)
  if grep -qE "^$1=" "$ENV_FILE"; then
    KEY="$1" VALUE="$2" awk 'BEGIN{FS=OFS="="} $1==ENVIRON["KEY"] && !done {print ENVIRON["KEY"] "=" ENVIRON["VALUE"]; done=1; next} {print}' "$ENV_FILE" > "$tmp"
  else
    cat "$ENV_FILE" > "$tmp"; printf '%s=%s\n' "$1" "$2" >> "$tmp"
  fi
  cat "$tmp" > "$ENV_FILE"; rm -f "$tmp"
}

random_hex() { openssl rand -hex 32; }

start_database() {
  if [ "$DB_MODE" = bundled ]; then
    say "Starting the bundled PostgreSQL..."
    $COMPOSE up -d --wait postgres
  else
    docker network inspect "$DB_NETWORK" >/dev/null 2>&1 \
      || die "Docker network '${DB_NETWORK}' not found (MOCKAN_DB_NETWORK). Is the shared PostgreSQL running?"
    say "Using the external database on Docker network '${DB_NETWORK}'"
  fi
}

# ── Preflight ────────────────────────────────────────────────────────────────
command -v docker >/dev/null 2>&1 || die "Docker is not installed."
compose_version=$(docker compose version --short 2>/dev/null || true)
[ -n "$compose_version" ] || die "Docker Compose v2 is required (docker compose)."
major=${compose_version#v}; minor=${major#*.}; major=${major%%.*}; minor=${minor%%.*}
if [ "$major" -lt 2 ] || { [ "$major" -eq 2 ] && [ "$minor" -lt 24 ]; }; then
  die "Docker Compose >= 2.24 is required (found ${compose_version})."
fi
command -v openssl >/dev/null 2>&1 || die "openssl is required to generate secrets."
[ -f docker-compose.prod.yml ] || die "Run this from deploy/compose (docker-compose.prod.yml not found)."

# ── .env: create, fill generated values, validate ────────────────────────────
if [ ! -f "$ENV_FILE" ]; then
  if [ "$DRY_RUN" = true ]; then
    say "[dry-run] would create ${ENV_FILE} from ${ENV_TEMPLATE}"
    ENV_FILE="$ENV_TEMPLATE"
  else
    cp "$ENV_TEMPLATE" "$ENV_FILE"; chmod 600 "$ENV_FILE"
    say "Created ${ENV_FILE} from ${ENV_TEMPLATE}"
  fi
fi

DB_MODE=$(env_get MOCKAN_DB_MODE); DB_MODE=${DB_MODE:-bundled}
DB_NETWORK=$(env_get MOCKAN_DB_NETWORK); DB_NETWORK=${DB_NETWORK:-pg}
case "$DB_MODE" in
  bundled) ;;
  external) COMPOSE="$COMPOSE -f docker-compose.external-db.yml" ;;
  *) die "MOCKAN_DB_MODE must be bundled or external (found: ${DB_MODE})." ;;
esac

generated=()
if [ "$DB_MODE" = bundled ]; then
  if [ -z "$(env_get POSTGRES_PASSWORD)" ]; then
    generated+=(POSTGRES_PASSWORD)
    if [ "$DRY_RUN" = false ]; then env_set POSTGRES_PASSWORD "$(random_hex)"; fi
  fi
  if [ -z "$(env_get MOCKAN_DATABASE_URL)" ]; then
    generated+=(MOCKAN_DATABASE_URL)
    if [ "$DRY_RUN" = false ]; then
      env_set MOCKAN_DATABASE_URL "postgresql+asyncpg://mockan:$(env_get POSTGRES_PASSWORD)@postgres:5432/mockan"
    fi
  fi
fi
if [ -z "$(env_get MOCKAN_SESSION_SECRET)" ]; then
  generated+=(MOCKAN_SESSION_SECRET)
  if [ "$DRY_RUN" = false ]; then env_set MOCKAN_SESSION_SECRET "$(random_hex)"; fi
fi
if [ "${#generated[@]}" -gt 0 ]; then
  if [ "$DRY_RUN" = true ]; then
    say "[dry-run] would generate: ${generated[*]}"
  else
    say "Generated ${generated[*]} in ${ENV_FILE} (not shown)"
  fi
fi

missing=()
for key in MOCKAN_DATABASE_URL MOCKAN_PUBLIC_BASE_URL MOCKAN_ALLOWED_UPSTREAM_HOSTS MOCKAN_OIDC_ISSUER \
           MOCKAN_OIDC_CLIENT_ID MOCKAN_OIDC_CLIENT_SECRET MOCKAN_ADMIN_SSO_SUBJECTS; do
  if [ -z "$(env_get "$key")" ] && [[ " ${generated[*]-} " != *" $key "* ]]; then missing+=("$key"); fi  # dry-run: still to be generated
done

problems=()
base_url=$(env_get MOCKAN_PUBLIC_BASE_URL)
if [ -n "$base_url" ]; then
  case "$base_url" in
    https://*) ;;
    http://*)  warn "MOCKAN_PUBLIC_BASE_URL is http://: sign-in cookies and tokens should travel over https." ;;
    *)         problems+=("MOCKAN_PUBLIC_BASE_URL must start with https:// (or http://)") ;;
  esac
fi
for key in MOCKAN_ALLOWED_UPSTREAM_HOSTS MOCKAN_ADMIN_SSO_SUBJECTS; do
  value=$(env_get "$key")
  if [ -n "$value" ]; then
    case "$value" in
      \[*\]) ;;
      *) problems+=("$key must be a JSON list, e.g. [\"a\",\"b\"]") ;;
    esac
  fi
done
db_url=$(env_get MOCKAN_DATABASE_URL)
if [ -n "$db_url" ]; then
  case "$db_url" in
    postgresql+asyncpg://*) ;;
    *) problems+=("MOCKAN_DATABASE_URL must start with postgresql+asyncpg://") ;;
  esac
fi
password=$(env_get POSTGRES_PASSWORD)
if [ -n "$password" ] && ! printf '%s' "$password" | grep -qE '^[A-Za-z0-9._~-]+$'; then
  problems+=("POSTGRES_PASSWORD may only contain letters, digits and . _ ~ - (it is placed in a URL)")
fi
secret=$(env_get MOCKAN_SESSION_SECRET)
if [ -n "$secret" ] && [ "${#secret}" -lt 32 ]; then
  problems+=("MOCKAN_SESSION_SECRET must be at least 32 characters")
fi

if [ "${#missing[@]}" -gt 0 ] || [ "${#problems[@]}" -gt 0 ]; then
  echo
  if [ "${#missing[@]}" -gt 0 ]; then
    echo "✗ Fill these in .env (see ${ENV_TEMPLATE} for what each one is):" >&2
    for key in "${missing[@]}"; do echo "    - ${key}" >&2; done
  fi
  if [ "${#problems[@]}" -gt 0 ]; then
    echo "✗ Fix these in .env:" >&2
    for item in "${problems[@]}"; do echo "    - ${item}" >&2; done
  fi
  if [[ " ${missing[*]} " == *" MOCKAN_OIDC_CLIENT_ID "* ]]; then
    origin=$(printf '%s' "${base_url:-https://<your-domain>}" | sed -E 's#^(https?://[^/]+).*#\1#')
    echo "  Register this redirect URI in Keycloak: ${origin}/api/v1/auth/callback" >&2
  fi
  echo "  Then run ./deploy.sh again." >&2
  exit 1
fi
say "${ENV_FILE} is complete ✓"

# ── Which tag ────────────────────────────────────────────────────────────────
current_tag=$(env_get IMAGE_TAG); current_tag=${current_tag:-latest}
if [ "$ROLLBACK" = true ]; then
  [ -f "$TAG_FILE" ] || die "Nothing to roll back to (${TAG_FILE} not found)."
  IMAGE_TAG=$(cat "$TAG_FILE")
elif [ -n "$TAG_ARG" ]; then
  IMAGE_TAG="$TAG_ARG"
else
  IMAGE_TAG="${IMAGE_TAG:-latest}"
fi
export IMAGE_TAG
REPO=$(env_get MOCKAN_IMAGE_REPO); REPO=${REPO:-ghcr.io/modarreszadeh/mockan}

if [ "$DRY_RUN" = true ]; then  # secrets that would be generated don't exist yet: render with placeholders
  for key in ${generated[@]+"${generated[@]}"}; do export "$key=dry-run-placeholder-dry-run-placeholder"; done
fi
$COMPOSE config -q || die "docker compose could not render the production configuration."

# ── Dry run stops here ───────────────────────────────────────────────────────
if [ "$DRY_RUN" = true ]; then
  echo
  say "[dry-run] plan, nothing was changed:"
  echo "    1. pull  ${REPO}/admin:${IMAGE_TAG}  and  ${REPO}/gateway:${IMAGE_TAG}"
  if [ "$DB_MODE" = bundled ]; then
    echo "    2. start the bundled PostgreSQL and wait until it is healthy"
  else
    echo "    2. check the external database is reachable on Docker network '${DB_NETWORK}'"
  fi
  echo "    3. stop nginx, gateway and admin, then run: alembic upgrade head"
  echo "    4. start everything, wait for health, probe the Panel and the Gateway through nginx"
  echo "    5. remember ${current_tag} in ${TAG_FILE} (for --rollback), set IMAGE_TAG=${IMAGE_TAG}"
  exit 0
fi

# ── --check-db ───────────────────────────────────────────────────────────────
if [ "$CHECK_DB" = true ]; then
  start_database
  say "Current database revision:"
  $COMPOSE run --rm --no-deps admin alembic current
  say "Latest revision in image ${IMAGE_TAG}:"
  $COMPOSE run --rm --no-deps admin alembic heads
  exit 0
fi

say "Deploying Mockan: tag ${IMAGE_TAG} (currently ${current_tag})"

# ── Pull ─────────────────────────────────────────────────────────────────────
aux_services=(nginx)
if [ "$DB_MODE" = bundled ]; then aux_services+=(postgres); fi
if [ "$NO_PULL" = false ]; then
  say "Pulling images from GHCR..."
  # nginx/postgres come from a public registry that may be blocked: pull them only when missing.
  if ! $COMPOSE pull admin gateway || ! $COMPOSE pull --policy missing "${aux_services[@]}"; then
    warn "Pull failed. Check the tag exists, or for a private package: docker login ghcr.io -u <user>"
    die "Nothing was stopped: the running version is untouched."
  fi
else
  say "Skipping image pull (--no-pull)"
fi

# ── Database first, so a failure here costs no downtime ──────────────────────
start_database

say "Checking the database connection (nothing has been stopped yet)..."
if ! $COMPOSE run --rm --no-deps -T admin python - <<'PY'
import asyncio, os
import asyncpg

async def main() -> None:
    dsn = os.environ["MOCKAN_DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://", 1)
    conn = await asyncpg.connect(dsn, timeout=10)
    print("  connected as", await conn.fetchval("select current_user"))
    await conn.close()

asyncio.run(main())
PY
then
  die "Cannot connect to the database with MOCKAN_DATABASE_URL. Nothing was stopped: the running version is untouched."
fi

say "Stopping app containers for the migration..."
$COMPOSE stop nginx gateway admin >/dev/null 2>&1 || true

say "Running database migrations..."
if ! $COMPOSE run --rm --no-deps admin alembic upgrade head; then
  warn "Migration failed. Restarting the previous containers."
  $COMPOSE start admin gateway nginx >/dev/null 2>&1 || true
  die "Deploy aborted; ${current_tag} is running again (it may need the old schema)."
fi

# ── Start ────────────────────────────────────────────────────────────────────
if [ "$current_tag" != "$IMAGE_TAG" ]; then printf '%s\n' "$current_tag" > "$TAG_FILE"; fi
env_set IMAGE_TAG "$IMAGE_TAG"

say "Starting services..."
if ! $COMPOSE up -d --no-build --remove-orphans --wait; then
  $COMPOSE ps
  $COMPOSE logs --tail=30 admin gateway
  die "Services did not become healthy. Roll back with: ./deploy.sh --rollback"
fi

# ── Probe through nginx ──────────────────────────────────────────────────────
bind=$(env_get MOCKAN_BIND); bind=${bind:-127.0.0.1}; [ "$bind" = "0.0.0.0" ] && bind=127.0.0.1
port=$(env_get MOCKAN_PORT); port=${port:-8765}
if command -v curl >/dev/null 2>&1; then
  say "Probing http://${bind}:${port} ..."
  ok=true
  curl -fsS -o /dev/null --max-time 5 "http://${bind}:${port}/api/v1/openapi.json" || { warn "Admin (/api) did not answer"; ok=false; }
  curl -fsS -o /dev/null --max-time 5 "http://${bind}:${port}/mock/_mockan/health/live" || { warn "Gateway (/mock) did not answer"; ok=false; }
  [ "$ok" = true ] || die "A probe failed. Roll back with: ./deploy.sh --rollback"
  say "Panel/Admin and Gateway answer through nginx ✓"
else
  warn "curl not found: skipped the probe"
fi

say "Pruning unused images..."
docker image prune -f >/dev/null

echo
echo "✓ Deployment complete: tag ${IMAGE_TAG}"
echo "  Local entry point : http://${bind}:${port}  (put your TLS proxy in front of this)"
echo "  Public base URL   : ${base_url}"
if [ -f "$TAG_FILE" ]; then echo "  Roll back         : ./deploy.sh --rollback  (to $(cat "$TAG_FILE"))"; fi
echo
