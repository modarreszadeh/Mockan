<h1 align="center">Mockan<span>.</span></h1>

<p align="center">
  <strong>Mock only the endpoints that don't exist yet. Everything else goes to the real backend.</strong><br>
  A personal mock gateway for frontend developers: no mock code in your app, just a base URL.
</p>

<p align="center">
  <img alt="Python 3.14" src="https://img.shields.io/badge/python-3.14-3776ab?logo=python&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white">
  <img alt="React 19" src="https://img.shields.io/badge/React-19-61dafb?logo=react&logoColor=black">
  <img alt="PostgreSQL" src="https://img.shields.io/badge/PostgreSQL-18-336791?logo=postgresql&logoColor=white">
</p>

<p align="center">
  <img src="docs/frontend/screenshots/scr-03-overview-1440.png" alt="The Mockan Panel overview: your base URL, active mocks and a getting-started checklist" width="860">
</p>

## Why Mockan

You are building a new screen, but the endpoint behind it isn't deployed yet. A classic mock server replaces the *whole* API, so you lose login, tokens and every page that already works. The usual workarounds are environment-variable juggling or `if (mock)` branches in your code, and both leave throw-away code that has to be removed before you push.

Mockan sits between your app and the real backend:

```mermaid
flowchart LR
    App["Your app<br/>(localhost)"] -->|"VITE_API_BASE_URL=<br/>https://mock.example.com/you"| GW["Mockan Gateway"]
    GW -->|"matches one of your rules"| Mock["Mock response"]
    GW -->|"everything else"| Real["Real backend<br/>(dev / stage)"]
    Panel["Panel<br/>(rules, log, services)"] -.->|"Admin API + PostgreSQL"| GW
```

- Requests that match one of your **rules** get your mock response.
- Every other request is **proxied unchanged** to the real service, so login, token refresh and existing pages keep working.
- Your frontend diff contains **no mock code**. When the real endpoint ships, disable the rule and nothing else changes.

## Features

**Mocking**
- **Isolated workspaces.** Everyone gets their own address (`/{slug}/...`); your rules never affect a teammate and theirs never affect you.
- **Flexible matching.** `Exact`, `Template` (`/orders/{id}`), `Prefix` and `Regex` (linear-time RE2, so no catastrophic patterns), plus optional method, query and header conditions. A deterministic precedence decides which rule wins.
- **Static or templated responses.** Set status, headers, content type, body and an artificial delay. Templated bodies (Jinja2 sandbox) can use the request, route parameters and a whitelist of [Faker](https://faker.readthedocs.io/) generators.
- **Scenarios.** Keep several named responses per rule (`success`, `empty`, `error-500`) and switch between them in one click.
- **Live in about 2 seconds.** Changes reach every Gateway replica without a restart.
- **Enable or disable** a single rule, or all of them, to compare against the real endpoint.

**Proxy that behaves**
- **Transparent reverse proxy.** Method, path, query, headers and body are preserved. Streaming, large uploads and downloads, SSE and WebSockets work without full buffering.
- **Browser-ready.** Preflight requests are answered, CORS headers are normalized, `Location` headers and cookies are rewritten for the gateway URL.
- **Multi-service routing.** A catalog of services, each with a path prefix and `dev` / `stage` base URLs. Pick the environment per service.
- **Always labeled.** Every response carries `X-Mockan-Source: mock | proxy | error`, so you never mistake fake data for real data.

**Productivity**
- **Live request log** with a **Mock this** button that turns a real, logged response into a rule.
- **Test route:** ask what *would* happen to a request (which rule, which upstream) without sending it.
- **Export / import** rules as JSON to share a mock set or keep it beside a branch.

**Operations**
- Stateless Gateway replicas, health and readiness endpoints, plus OpenTelemetry metrics and opt-in tracing exported over OTLP.
- Upstream **host allowlist** (Mockan is never an open proxy), secrets masked in logs, OIDC sign-in (for example Keycloak).

<p align="center">
  <img src="docs/frontend/screenshots/scr-05-rule-editor-1440.png" alt="The rule editor with match type, pattern and a live summary of the response" width="860">
</p>

<p align="center">
  <img src="docs/frontend/screenshots/scr-09-log-details-1440.png" alt="A logged request with its headers and JSON body, and a Mock this button" width="860">
</p>

## Quick start

You need [Docker](https://docs.docker.com/get-docker/) with Compose.

```bash
git clone https://github.com/modarreszadeh/Mockan.git
cd Mockan/deploy/compose
docker compose --profile demo up --build
```

| What | Where |
| --- | --- |
| Panel and Admin API | <http://localhost:8081> |
| Gateway replicas | <http://localhost:8090>, <http://localhost:8091> |
| PostgreSQL | `localhost:5432` (user, password and database `mockan`) |

Set `MOCKAN_DB_PORT=5433` if port 5432 is taken. The `demo` profile adds a tiny fake backend (`fake-upstream:9000`) to proxy to.

Then try the whole journey from the command line:

```bash
A=http://localhost:8081; H='content-type: application/json'
curl -c jar -s "$A/api/v1/auth/login" -o /dev/null                          # sign in (dev mode)
curl -b jar -X PUT  -H "$H" -d '{"slug":"ehtesham"}' $A/api/v1/me             # claim your address
curl -b jar -X POST -H "$H" -d '{"name":"limsa","pathPrefix":"/limsa"}' $A/api/v1/services   # note the id
curl -b jar -X POST -H "$H" -d '{"environment":"stage","baseUrl":"http://fake-upstream:9000"}' \
     $A/api/v1/services/<id>/environments

curl -i http://localhost:8090/ehtesham/limsa/api/v1/dashboard                # X-Mockan-Source: proxy
```

Now open the Panel, create a rule for `GET /limsa/api/v1/dashboard`, and repeat the last request: within about 2 seconds it returns your mock with `X-Mockan-Source: mock`. Point your app at it:

```bash
# .env
VITE_API_BASE_URL=http://localhost:8090/ehtesham
```

> [!WARNING]
> The compose stack runs with `MOCKAN_AUTH_MODE=dev`: anyone who can reach the Admin can sign in as anyone. It is for local use only. Never run dev mode on a shared network; configure OIDC instead (see [operations](docs/backend/operations.md)). Mockan is a development tool and is not meant to serve production traffic or to be exposed to the internet.

## How it works

Mockan is two processes that share a PostgreSQL database:

| Part | Role | Stack |
| --- | --- | --- |
| **Gateway** (`mockan.gateway`) | Data plane. Resolves the developer and service from the path, matches rules against an in-memory snapshot, answers with a mock or streams the request upstream. Stateless; scale by adding replicas. | FastAPI, Uvicorn, `httpx`, `websockets`, RE2 |
| **Admin** (`mockan.admin`) | Control plane. Admin API, sign-in, migrations, live-log WebSocket, and it serves the Panel. | FastAPI, SQLAlchemy 2 (async), Alembic |
| **Panel** (`panel/`) | The web UI where you claim a slug and manage rules, services, the log and settings. | React 19, TypeScript, Vite, Tailwind CSS v4, shadcn/ui, TanStack Query |

Rule changes are written to PostgreSQL and announced with `LISTEN/NOTIFY`; each Gateway rebuilds its snapshot, with a periodic reload as a safety net.

## Repository layout

```
server/        Python backend: Gateway + Admin (one uv project, one `mockan` package)
panel/         React single-page app, built into the Admin image
deploy/        Docker images and the local Compose stack
docs/          All documentation (see docs/README.md)
  product/       Product requirements, personas, user journey
  backend/       Backend design, conventions and operations
  frontend/      Panel design tokens, components, screens and conventions
  agent/         System architecture and the rules coding agents follow
CONTEXT.md     Project glossary
```

## Development

**Backend** (Python 3.14 and [uv](https://docs.astral.sh/uv/)):

```bash
cd server
uv sync
docker compose -f ../deploy/compose/docker-compose.yml up -d postgres
uv run alembic upgrade head
uv run uvicorn mockan.admin.app:create_app --factory --port 8081 --reload
uv run uvicorn mockan.gateway.app:create_app --factory --port 8080 --reload
./scripts/check.sh      # lint + format + mypy + import contracts + tests
```

**Panel** (Node.js and npm):

```bash
cd panel
npm ci
npm run dev             # http://localhost:5173 with a mock backend (MSW); /__design is the style guide
npm run check           # typecheck + lint + tests + build
npm run e2e             # Playwright end-to-end journey
```

To develop the Panel against a real Admin, run the Admin on port 8081 and start the Panel with `VITE_USE_MSW=false npm run dev`.

Database tests use Testcontainers and need Docker; `uv run pytest -m "not db"` skips them.

## Documentation

All project documentation is Markdown, written to be read by people and by AI coding agents alike.

| Start here | |
| --- | --- |
| [Product requirements](docs/product/mockan-prd.md) | What Mockan does, for whom and why. |
| [Architecture](docs/agent/mockan-architecture.md) | The system design: request lifecycle, matching, data model, Admin API. |
| [Backend docs](docs/backend/README.md) | Stack, structure, Gateway, Admin API, database, operations, testing. |
| [Frontend docs](docs/frontend/README.md) | Design tokens, components, screens, conventions, testing. |
| [Glossary](CONTEXT.md) | MockRule, Scenario, Request log and the other terms used throughout. |

## Status

Phase 1 (workspaces, proxy, matching, static mocks, Panel) and Phase 2 (scenarios, live log, test route, export/import, templated bodies, operability) are built. Phase 3 (contract-driven features) is not planned yet.

## Contributing

Issues and pull requests are welcome. Please:

- Read the [glossary](CONTEXT.md) and use its terms in code and docs.
- Run `./scripts/check.sh` (backend) and `npm run check` (Panel) before you push.
- Update the matching Markdown document in the same pull request as any change to behavior, schema, API or structure.
