---
title: Mockan — Product Requirements Document
status: Draft (v0.1)
date: 2026-10-03
owner: Product / Backend team
source: Agent/mockan-architecture.md (Approved baseline v1.0)
audience: Product, frontend & backend engineering leads, platform/DevOps, AI coding agents
---

# Mockan — Product Requirements Document

> **In one sentence:** Mockan lets a frontend developer build against an API that does not exist yet by pointing their app at a personal gateway that proxies to the real backend for everything *except* the routes they choose to mock. Their frontend code never contains anything mock-specific.

This PRD covers **what** Mockan must do and **why**. The **how** is in [`Agent/mockan-architecture.md`](../Agent/mockan-architecture.md). Requirement IDs (`FR-xx`, `NFR-xx`), decision IDs (`D-xx`) and open-question IDs (`OQ-xx`) refer to that document. New product-level IDs in this PRD use the `PR-xx` prefix (product requirement), `US-xx` (user story) and `C-xx` (project constraint).

> **Key constraint (C-01, §4):** all Mockan documentation — product, frontend and backend — is written in Markdown and must be AI-agent-friendly.

---

## 1. Problem statement

**Frontend developers can't build a feature until its backend API exists, and today's workarounds produce code that can't be shipped.**

Classic mock servers replace the *whole* API, so a developer working on one new page (for example a new screen in *Limsa*) loses login, tokens, the portal and every other page that already works. To get around this, developers either keep switching environment variables or hard-code conditionals that send some calls to a mock and others to the real server. Both leave throw-away code in the frontend that must be removed before it can be pushed. That means extra rework, review noise and a real risk of mock logic reaching stage.

**Who is affected:** every frontend engineer whose feature depends on an endpoint that is still in development. In a microservice setup this happens on most new features.

**Cost of not solving it:**
- Frontend work is blocked or serialised behind backend delivery, which stretches feature lead time.
- Rework: mock-specific code has to be written, then removed and re-tested.
- Integration bugs show up late, because the frontend was never exercised against the real auth/session flow while it was being built.
- Contract drift: there is no shared, explicit place where the agreed response shape lives while the backend is being built.

---

## 2. Goals

| # | Goal | Type | How we know it worked |
| --- | --- | --- | --- |
| G1 | **Zero mock-specific code in frontend repos.** A feature built against Mockan is pushed to stage with no code changes beyond the base URL in `.env`. | User | 100% of Mockan-assisted features merged with no mock conditionals (checked in PR review). |
| G2 | **Unblock frontend work from backend delivery.** Frontend work can start as soon as the API contract is agreed, not when the endpoint is deployed. | Business | Median gap between "contract agreed" and "frontend work started" drops below 1 working day. |
| G3 | **The real system keeps working while mocking.** Login, tokens and unrelated pages work through Mockan exactly as they do against stage. | User | Proxy pass-through fidelity: no proxy-caused defects reported per month after 4 weeks of use. |
| G4 | **Fast feedback loop.** Changing a mock is as quick as editing a file. | User | Rule change visible in the gateway in ≤ 2 s (FR-08); a first mock created in ≤ 5 minutes after first login. |
| G5 | **Safe by construction.** Mockan can't be used as an open proxy or reach production. | Business | Zero upstream requests to hosts outside the allowlist; zero unmasked secrets in logs (NFR-06, NFR-07). |

---

## 3. Non-goals

| Non-goal | Why it's out of scope |
| --- | --- |
| **A production API gateway.** Mockan never serves end users or production traffic. | Different reliability, security and scale requirements; it would turn a dev tool into critical infrastructure. |
| **Contract testing or consumer-driven contract verification** (Pact-style). | Separate discipline with its own tooling. Phase 3 "diff alerts" only point in this direction (P2). |
| **Load or performance testing.** | Mockan adds a hop and artificial delays; its numbers say nothing about the real system. |
| **Replacing backend integration tests.** | Mocks describe the *intended* contract, not verified behaviour. |
| **Per-team or shared workspaces in v1.** One workspace per person (D-01). | Isolation is the core promise. Shared rule sets are a Phase 3 consideration (P2). |
| **Mocking by request body content.** | Adds matching complexity and ambiguity; deferred to Phase 3. |
| **Access from outside the internal network/VPN.** | Security posture (NFR-05); there is no auth on the gateway (D-12). |

---

## 4. Key project constraints

### C-01 Documentation is Markdown-only and AI-agent-friendly

**Everything about Mockan is documented in Markdown (`.md`), written so an AI coding agent can read, follow and update it as reliably as a human.** This is a project-wide constraint, not a style preference: AI agents are expected to implement large parts of Mockan, and they can only be as correct as the docs they read.

**Scope — applies to every layer:**

| Layer | Folder | Must be documented (at minimum) |
| --- | --- | --- |
| Product | `Product/` | PRD, product design / UX flows, personas, roadmap and phase scope, decisions and open questions. |
| Frontend (Panel) | `Frontend/` | Architecture, folder structure, routing, state management, API client, component catalogue (props, states, usage), design tokens, conventions. |
| Backend | `Backend/` | Architecture, database schema and migrations policy, domain model, Admin API contract, Gateway pipeline, code style and conventions, testing strategy. |
| Cross-cutting | `Agent/` | System architecture and the rules agents must follow across layers. |

**What "AI-agent-friendly" means (acceptance criteria for every doc):**
- [ ] **Markdown only.** No `.docx`, PDF, slides, wiki-only pages or images as the only source of truth. Diagrams are written as Mermaid inside the `.md` file; any image is a supplement, never the only copy of the information.
- [ ] **YAML front matter** at the top with at least `title`, `status`, `date`, `owner`, and `source`/`related` links when the doc derives from another.
- [ ] **One topic per file**, with a short summary at the top that says what the file covers and who it is for.
- [ ] **Stable IDs** for everything that can be referenced: requirements (`FR-`, `NFR-`, `PR-`), decisions (`D-`), open questions (`OQ-`), constraints (`C-`), user stories (`US-`). IDs are never reused or renumbered; retired items are marked as such.
- [ ] **Normative terms** come from the glossary (`Agent/mockan-architecture.md` §2) and are used exactly as written, in docs and in code.
- [ ] **Explicit over implied:** rules use MUST / MUST NOT / SHOULD; tables and checklists rather than long prose; concrete examples (paths, payloads, commands) instead of descriptions.
- [ ] **Undecided items are labelled** as open questions with a stated default, so an agent knows what to build and where to leave a `TODO(OQ-xx)` marker.
- [ ] **Relative links** between docs (e.g. `../Agent/mockan-architecture.md`), so they work in the repo, in an editor and for an agent reading files.
- [ ] **Docs change with the code.** A PR that changes behaviour, schema, API or structure updates the matching doc in the same PR; reviewers reject PRs where they disagree.

**Why:** AI agents can't ask hallway questions or open a design tool. If something isn't in a Markdown file in the repo, an agent will guess, and guesses are where drift and rework come from.

---

## 5. Personas

| Persona | Description | Primary needs |
| --- | --- | --- |
| **Frontend Developer** (primary) | Builds web apps (e.g. Limsa, Portal) on `localhost`. Owns one Mockan workspace. | Real login and real data for finished parts; controllable fake responses for unfinished parts; no code changes to switch. |
| **Backend Developer** | Owns a microservice and agrees API contracts with frontend. | A way to hand over a contract ("assume I've delivered this") and see whether the frontend is calling it as expected. |
| **Mockan Admin** (platform/DevOps or tech lead) | Maintains the Service catalog and operates Mockan. | Register services and dev/stage URLs safely; keep production and arbitrary hosts unreachable; observe health. |
| **QA / Reviewer** (secondary) | Reproduces edge cases (empty lists, 500s, slow responses). | Switch a route to an error or empty scenario without backend help. |

---

## 6. Core user journey (Phase 1 exit scenario)

1. Ehtesham signs in to the Mockan panel with company SSO and claims the slug `ehtesham`.
2. The panel shows the base URL to use: `VITE_API_BASE_URL=https://mock.novin-tools.com/ehtesham`.
3. He sets that value in `.env` and starts the app. Login, token refresh and the existing portal all work, because every request is **proxied** to stage.
4. The new dashboard endpoint `GET /limsa/api/v1/dashboard` isn't ready yet. He creates a rule with that pattern and pastes the agreed JSON from the backend contract.
5. Within 2 s the app gets the mocked dashboard. Every other call is still real. Responses show `X-Mockan-Source: mock` or `proxy`.
6. He builds the page and pushes it. **The frontend diff contains no mock code.**
7. The backend ships the real endpoint. He disables the rule; the same frontend code now hits the real API with no code changes.

---

## 7. User stories

Stories are ordered by priority within each persona. `→` shows the requirement(s) that deliver them.

### Frontend Developer
- **US-01** As a frontend developer, I want my own Mockan address, so that my mocks never affect teammates and theirs never affect me. → PR-01
- **US-02** As a frontend developer, I want every request I haven't mocked to reach the real backend unchanged, so that login, tokens and existing pages keep working. → PR-02, PR-03
- **US-03** As a frontend developer, I want to mock a single route by method and path, so that I can build against an endpoint that isn't deployed yet. → PR-05, PR-06
- **US-04** As a frontend developer, I want to mock route families (`/orders/{id}`, a prefix, a regex), so that I don't need one rule per ID. → PR-05
- **US-05** As a frontend developer, I want my rule changes to take effect within seconds without restarting anything, so that iterating on a mock feels instant. → PR-07
- **US-06** As a frontend developer, I want to turn one rule, or all rules, off, so that I can check my code against the real endpoint the moment it ships. → PR-08
- **US-07** As a frontend developer, I want to choose dev or stage per service, so that I can use a backend feature that is only deployed to dev. → PR-04
- **US-08** As a frontend developer, I want to see in the response whether it was mocked or proxied, so that I never confuse fake data with real data. → PR-09
- **US-09** As a frontend developer, I want several named responses per rule (success, empty, error-500) and to switch between them with one click, so that I can build every UI state quickly. → PR-11
- **US-10** As a frontend developer, I want a live list of my recent requests and a "Mock this" button, so that I can create a mock from a real response instead of typing JSON by hand. → PR-12
- **US-11** As a frontend developer, I want to type a method and path and see what would happen, so that I can debug why a route is (or isn't) being mocked. → PR-13
- **US-12** As a frontend developer, I want to add an artificial delay to a mock, so that I can build and test loading states. → PR-06
- **US-13** As a frontend developer, I want to export my rules as JSON and import them, so that I can share a mock set with a teammate or keep it next to my branch. → PR-14

### Backend Developer
- **US-20** As a backend developer, I want to give a frontend developer a contract file they can import, so that they can start work before my endpoint is deployed. → PR-14 (P1), PR-20 (P2)
- **US-21** As a backend developer, I want requests through Mockan to carry the developer's identity, so that I can correlate them in my service logs. → PR-03

### Mockan Admin
- **US-30** As a Mockan admin, I want to register a service with its path prefix and dev/stage base URLs, so that developers can reach it without entering URLs themselves. → PR-10
- **US-31** As a Mockan admin, I want upstream hosts limited to an allowlist that never includes production, so that Mockan can't be misused as an open proxy. → PR-15
- **US-32** As a Mockan admin, I want health and metrics endpoints, so that I can tell whether the gateway is serving fresh rules. → PR-17

### QA / Reviewer
- **US-40** As a QA engineer, I want to switch a route to an error or empty scenario, so that I can verify error handling without a backend change. → PR-11

### Edge cases and error states
- **US-50** As a frontend developer who mistyped my slug, I want a clear `developer_not_found` error, so that I know the problem is my base URL and not the backend. → PR-16
- **US-51** As a frontend developer calling a path that no registered service owns, I want a clear `service_not_resolved` error, so that I can ask an admin to add the service. → PR-16
- **US-52** As a frontend developer, I want a clear `upstream_unreachable` / `upstream_timeout` error when the real backend is down, so that I don't blame Mockan or my code. → PR-16
- **US-53** As a frontend developer whose workspace has no rules yet, I want the panel to explain what to do next, so that the empty state is a starting point, not a dead end. → PR-18
- **US-54** As a frontend developer, I want browser calls from `localhost` to work without CORS errors for both mocked and proxied responses, so that I don't have to configure anything in the backend. → PR-03

---

## 8. Requirements

### 7.1 Must-have (P0) — Phase 1 MVP

Without these, a developer can't do the core journey in §6.

#### PR-01 Isolated developer workspaces — FR-01, D-01, D-02
Each Developer gets a workspace at `https://mock.novin-tools.com/{developerSlug}/`, created on first SSO login.
- [ ] On first SSO login with no slug, the developer is asked to pick a slug matching `^[a-z][a-z0-9-]{1,31}$`.
- [ ] Reserved slugs (`_*`, `api`, `hubs`, `health`) and slugs already in use are rejected with a clear message.
- [ ] Given developers A and B both have rules on the same path, when A's app calls it, then only A's rules are evaluated.
- [ ] A disabled Developer's address returns `404 developer_not_found`.

#### PR-02 Transparent reverse proxy — FR-02, NFR-04, D-04
Any request that matches no enabled rule is forwarded to the right upstream as-is.
- [ ] Method, path (after slug), query, headers and body are preserved.
- [ ] Large bodies, file uploads/downloads, SSE and WebSockets work without full buffering.
- [ ] Given a working app on stage, when its base URL points at Mockan with no rules, then login, token refresh and all existing pages behave the same as against stage.
- [ ] Gateway overhead ≤ 10 ms p95 for proxied requests, excluding upstream time (NFR-01).

#### PR-03 Browser compatibility: CORS, cookies, redirects — D-13, §6.3–6.4
Proxied and mocked responses must be readable by a browser app on `localhost`.
- [ ] Preflight `OPTIONS` is answered by Mockan with `204` and never forwarded.
- [ ] `Access-Control-Allow-Origin` echoes the Origin when it matches the Developer's `AllowedOrigins` (default `http://localhost:*`, `http://127.0.0.1:*`); credentials allowed.
- [ ] Upstream CORS headers are replaced by Mockan's.
- [ ] `Location` headers that point at the upstream are rewritten to the developer's Mockan URL.
- [ ] `Set-Cookie` has `Domain` removed and `Path` prefixed with `/{slug}`.
- [ ] Upstream requests carry `X-Mockan-Developer` and `X-Forwarded-Prefix: /{slug}`; `traceparent` is forwarded.
- [ ] A developer can edit their `AllowedOrigins` in the panel.

#### PR-04 Multi-service routing and environment choice — FR-03, FR-04
- [ ] The Service is resolved from the path after the slug using the **longest matching** `PathPrefix`.
- [ ] `StripPrefix` per Service decides whether the prefix is passed upstream.
- [ ] Per Developer, each Service's environment (`dev`/`stage`) can be chosen; the default is the Service default (`stage`).
- [ ] Changing the environment takes effect within 2 s.

#### PR-05 Mock rule matching — FR-05, D-09, §7
- [ ] Match types: `Exact` (case-insensitive, trailing slash ignored), `Template` (`/orders/{id}`), `Prefix`, `Regex`.
- [ ] Optional method filter (or `ANY`), optional query conditions and header conditions (equals / exists).
- [ ] When several rules match, the winner is chosen by: Priority (lower first) → match type (Exact > Template > Prefix > Regex) → longer pattern → older rule.
- [ ] Rules match the path **after** the slug, so they don't depend on the Mockan host name.
- [ ] Regex rules use a non-backtracking engine with a 50 ms timeout; an invalid regex is rejected when saved.
- [ ] Patterns for Exact/Template/Prefix must start with `/`.

#### PR-06 Static mock responses — FR-06, §7.3
- [ ] A rule returns a configured status code (100–599), headers, content type (default `application/json`) and body (≤ 1 MB).
- [ ] Optional delay 0–30,000 ms.
- [ ] The panel validates JSON bodies before saving and shows the error location.

#### PR-07 Changes apply within 2 seconds — FR-08, NFR-02, D-07
- [ ] Given the gateway is running, when a developer saves, enables or disables a rule, then the next request after ≤ 2 s reflects the change, with no restart.
- [ ] The gateway never queries the database while handling a request.
- [ ] If the database is unreachable, the gateway keeps serving the last good rules and reports `ready = degraded`.

#### PR-08 Enable/disable rules — FR-11
- [ ] Each rule has an enable switch.
- [ ] A single "disable all / enable all" action exists for the workspace.
- [ ] Disabled rules stay saved and can be re-enabled without editing.

#### PR-09 Source transparency
- [ ] Every gateway response has `X-Mockan-Source: mock | proxy`; mocked responses also have `X-Mockan-Rule-Id`.
- [ ] Both headers are listed in `Access-Control-Expose-Headers` so frontend dev tools and code can read them.

#### PR-10 Service catalog (admin) — D-08
- [ ] Admins can create, edit and delete Services (name, path prefix, strip prefix, rewrite origin, default environment) and their dev/stage environments (base URL, timeout, extra headers).
- [ ] Non-admin developers can read the catalog but not change it.
- [ ] Path prefixes and service names are unique.

#### PR-15 Security guardrails — NFR-05, NFR-06, NFR-07, D-12
- [ ] Gateway and panel are reachable only from the internal network/VPN.
- [ ] The panel and Admin API require company SSO; developers can only see and change their own workspace.
- [ ] Upstream base URLs must have a host in `Mockan:AllowedUpstreamHosts`; production hosts are never allowed. Saving a non-allowed host is rejected.
- [ ] `Authorization`, `Cookie`, `Set-Cookie` and any header/JSON field matching `token|secret|password|api-key` are masked in all logs.
- [ ] Rule changes are recorded in an audit log (who, when, what).

#### PR-16 Clear Mockan errors — §14 rule 8
- [ ] Mockan-generated errors are RFC 7807 problem+json with a stable `code`: `developer_not_found` (404), `service_not_resolved` (502), `upstream_unreachable` (502), `upstream_timeout` (504), `mock_render_failed`.
- [ ] The error body includes the developer slug and the path tried, so the developer can see where it went wrong.

#### PR-18 Basic panel and onboarding — §11
- [ ] Onboarding: pick a slug; copyable base URL snippet for `.env`.
- [ ] Services screen: catalog list with environment dropdown per Service.
- [ ] Rules screen: list with enable switch, method, match type, pattern, active response; "disable all".
- [ ] Rule editor: match settings, conditions, response (status, headers, body with JSON editor and validation, delay).
- [ ] Empty states explain the next step (e.g. "No rules yet — all traffic is proxied. Create your first mock.").

### 7.2 Nice-to-have (P1) — Phase 2 "Productivity"

The core use case works without these, but they cut the time to create and debug mocks a lot.

#### PR-11 Multiple scenarios per rule — FR-07
- [ ] A rule can have several named MockResponses (e.g. `success`, `empty`, `error-500`); exactly one is active.
- [ ] Switching the active response is one action and takes effect within 2 s.
> Note: the data model supports this from Phase 1 (`active_response_id`); Phase 1 UI may expose only one response per rule. See OQ-P1.

#### PR-12 Live request log and "Mock this" — FR-09, D-10
- [ ] The panel shows the developer's recent requests live, with a `Proxied` / `Mocked` / `Error` badge, method, path, status and duration.
- [ ] Filter by source and path; a details drawer shows masked headers and body samples (≤ 16 KB).
- [ ] "Mock this" creates a rule pre-filled with the request's method/path and the real response's status, headers and body.
- [ ] Logging never slows down or blocks requests; if the log buffer is full, entries are dropped and counted.
- [ ] Retention: last 7 days and at most 5,000 entries per developer.

#### PR-13 Test-route tool — FR-10
- [ ] Given a method, path and optional headers/query, the panel shows the matching rule (and why it won), or the upstream URL it would be proxied to, or the error it would produce.
- [ ] Uses the same matching logic as the gateway, so the answer is always the same as real behaviour.

#### PR-14 Export / import — FR-12
- [ ] Export all rules (with responses) as a JSON file.
- [ ] Import a JSON file; the user chooses to merge or replace; invalid entries are reported and nothing partial is saved silently.

#### PR-19 Templated response bodies — §7.3 Phase 2
- [ ] Response bodies can be templates with access to request path, query, headers and route parameters (e.g. echo `{id}`).
- [ ] Fake-data helpers (names, dates, numbers) for realistic lists.
- [ ] A template error returns `mock_render_failed` with the error message, not a blank 500.

#### PR-17 Operability
- [ ] `/_mockan/health/live` and `/_mockan/health/ready` endpoints; ready requires loaded rules.
- [ ] Metrics: requests by source, proxy duration, rule-snapshot age, dropped log entries.
- [ ] Structured logs include developer, service, source, rule id and trace id.

> PR-17 is P1 for the product, but health endpoints are needed for deployment; engineering may build them in Phase 1.

### 7.3 Future considerations (P2) — Phase 3 "Contract-driven"

Not in scope now. Design choices in Phases 1–2 should not make these hard.

| ID | Consideration | Design implication now |
| --- | --- | --- |
| PR-20 | **Import backend OpenAPI specs to generate rules.** | Keep rule/response schema close to OpenAPI concepts (method, path template, status, content type). |
| PR-21 | **Proxy-and-patch mode**: call the real endpoint, then apply a JSON Merge Patch to its response. | `body_mode` enum already reserves `ProxyAndPatch`. |
| PR-22 | **Drift alert**: warn when a real endpoint starts answering differently from its mock. | Keep request-log samples comparable to rule responses. |
| PR-23 | **Shared rule sets** between developers (e.g. a backend dev publishes a contract set). | Rules are owned by a Developer today; don't hard-code assumptions that block a future owner type. |
| PR-24 | **Body-content matching conditions.** | Conditions are stored as JSONB; new condition kinds can be added. |
| PR-25 | **Subdomain-based workspaces** (`{slug}.mock.novin-tools.com`). | Keep slug resolution in one place (OQ-01). |

---

## 9. Success metrics

Targets below are **proposed hypotheses** for a first internal rollout; confirm with engineering leads before adoption. Measurement comes from Mockan's own database and metrics unless stated otherwise.

### Leading indicators (days to weeks)

| Metric | Definition | Target (success / stretch) | Evaluate at |
| --- | --- | --- | --- |
| Activation | % of onboarded developers who create ≥ 1 enabled rule **and** have ≥ 1 proxied request in the same week | 70% / 90% | 2 and 4 weeks after launch |
| Time to first mock | Median time from first SSO login to first mocked response served | ≤ 10 min / ≤ 5 min | 4 weeks |
| Weekly active developers | Developers with ≥ 1 request through the gateway in a week, as % of frontend engineers | 50% / 80% | 4 and 8 weeks |
| Proxy fidelity | Bugs filed where Mockan's proxy changed behaviour vs. direct stage access | ≤ 2 in first month, 0 after | Monthly |
| Mock-to-proxy rate | Share of a developer's requests that are mocked (healthy: low, most traffic is real) | < 30% median | Monthly |
| Rule propagation | p95 time from save to gateway applying it (`mockan_snapshot_age_seconds`) | ≤ 2 s | Continuous |
| Gateway overhead | p95 added latency on proxied requests | ≤ 10 ms | Continuous |

### Lagging indicators (weeks to months)

| Metric | Definition | Target | Evaluate at |
| --- | --- | --- | --- |
| Zero mock code in PRs | % of Mockan-assisted features merged with no mock-specific frontend code (PR review checklist item) | 100% | Quarterly |
| Frontend start delay | Median working days between "API contract agreed" and "frontend work started" for features with new endpoints (from tracker) | < 1 day (baseline to be measured before launch) | 1 quarter |
| Integration defects | Defects found on stage caused by frontend/backend contract mismatch, per sprint | −30% vs. pre-launch baseline | 1 quarter |
| Developer satisfaction | Short survey: "Mockan made it easier to build ahead of the backend" (1–5) | ≥ 4.0 average | 1 quarter |
| Security incidents | Requests to non-allowlisted hosts; unmasked secrets found in logs | 0 | Continuous |

---

## 10. Open questions

Questions inherited from the architecture keep their `OQ-xx` IDs. New product questions use `OQ-Px`.

| ID | Question | Owner | Blocking? | Current default |
| --- | --- | --- | --- | --- |
| OQ-02 | Do our apps authenticate with bearer tokens or cookies? Cookies from `localhost` to another domain need `SameSite=None; Secure` and may break. | Frontend leads + Backend | **Blocking for Phase 1 exit** (it decides whether login works through Mockan) | Assume bearer tokens; implement Set-Cookie rewrite anyway. |
| OQ-04 | Which OIDC provider (Keycloak, Azure AD, other)? | Platform/DevOps | **Blocking** for panel login | Generic OIDC config. |
| OQ-05 | Do frontends call one shared API gateway URL or one base URL per microservice? | Frontend leads, per app | Blocking for catalog setup of each app, not for build | Both supported via `PathPrefix` + `StripPrefix`. |
| OQ-01 | Path-based (`/{slug}/`) or subdomain (`{slug}.mock…`) workspaces? | Engineering + DevOps | Non-blocking | Path-based. |
| OQ-03 | Panel on the same host (`/_mockan/admin`) or a separate host (`mockan.novin-tools.com`)? | DevOps | Non-blocking | Separate host if DNS/TLS is easy. |
| OQ-P1 | Architecture lists FR-07 (multiple responses) in both Phase 1 coverage and Phase 2 scope. Which phase does the *UI* for switching scenarios ship in? | Product + Engineering | Non-blocking | Data model in Phase 1, scenario switching UI in Phase 2 (PR-11 = P1). |
| OQ-P2 | Which apps and services are in the pilot (e.g. Limsa + Identity + Portal), and who are the pilot developers? | Product + Frontend leads | Blocking for rollout, not build | Limsa team as first pilot. |
| OQ-P3 | How do we measure the "frontend start delay" baseline — which tracker fields mark "contract agreed" and "frontend started"? | Product + Data | Non-blocking | Measure manually for the pilot team. |
| OQ-P4 | Should backend developers have their own workspace to publish contracts, or only through export/import until Phase 3? | Product + Backend leads | Non-blocking | Export/import only until Phase 3. |
| OQ-P5 | Who is the named operational owner of Mockan (on-call, catalog maintenance)? | Engineering management | Blocking for launch | Backend team. |

---

## 11. Timeline and phasing

No hard external deadline is known. Phases follow the architecture's delivery plan (§12.4); each phase ends with a demoable exit check.

| Phase | Scope (requirements) | Exit criteria | Dependencies |
| --- | --- | --- | --- |
| **1 — MVP** | PR-01 … PR-10, PR-15, PR-16, PR-18 (FR-01…FR-06, FR-08, FR-11; FR-07 data model) | One pilot frontend developer logs in to a real app through Mockan, mocks one unreleased endpoint, and pushes code with **no mock-specific changes** (journey §6). | OIDC provider details (OQ-04); internal DNS + TLS for `mock.novin-tools.com`; internal PostgreSQL; ingress IP restriction; answer to OQ-02. |
| **2 — Productivity** | PR-11, PR-12, PR-13, PR-14, PR-17, PR-19 (FR-07, FR-09, FR-10, FR-12) | Pilot developers routinely use scenarios and "Mock this"; time-to-first-mock target met. | Phase 1 feedback from the pilot. |
| **3 — Contract-driven** | PR-20 … PR-25 (to be selected) | Agreed after Phase 2 feedback. | Backend services publishing OpenAPI specs. |

**Suggested rollout:**
1. Internal dogfood by the backend team on one service.
2. Pilot with one frontend team (OQ-P2) for 2 weeks; collect baseline metrics before the pilot starts.
3. Open to all frontend developers; add the "no mock code" checklist item to PR templates.

---

## 12. Risks

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Cookie-based auth breaks through path-prefixed proxying (cross-site cookies from `localhost`). | Medium | High — login fails, core promise broken | Resolve OQ-02 early; test with each pilot app before rollout; subdomain mode (PR-25) as fallback. |
| Backends reject foreign `Origin`/`Host` or emit absolute URLs. | Medium | Medium | `RewriteOrigin` flag; Location rewrite; per-service checks during catalog setup. |
| Mocks drift from the final real API and the frontend breaks when the mock is disabled. | Medium | Medium | Encourage "Mock this" from real responses; export mocks with the contract; drift alerts in Phase 3. |
| Developers forget enabled mocks and get confused by stale data. | Medium | Low | `X-Mockan-Source` header; rules list prominent; "disable all". |
| Mockan becomes a shared dependency; its downtime blocks frontend work. | Low | Medium | ≥ 2 gateway replicas; keeps serving last rules if DB is down; developers can always switch `.env` back to stage. |
| Secrets leak through request logs. | Low | High | Masking rules (PR-15), short retention, internal-only access. |

---

## 13. Appendix — traceability

| PRD requirement | Architecture refs | Priority |
| --- | --- | --- |
| PR-01 Workspaces | FR-01, D-01, D-02 | P0 |
| PR-02 Transparent proxy | FR-02, NFR-01, NFR-03, NFR-04, D-04 | P0 |
| PR-03 CORS / cookies / redirects | D-13, §6.3, §6.4 | P0 |
| PR-04 Multi-service + environment | FR-03, FR-04 | P0 |
| PR-05 Matching | FR-05, NFR-08, D-09, §7.1–7.2 | P0 |
| PR-06 Static responses | FR-06, §7.3 | P0 |
| PR-07 Hot reload | FR-08, NFR-02, D-07 | P0 |
| PR-08 Enable/disable | FR-11 | P0 |
| PR-09 Source headers | §6.3, §14 rule 7 | P0 |
| PR-10 Service catalog | D-08, §10 | P0 |
| PR-15 Security guardrails | NFR-05, NFR-06, NFR-07, D-12, §12.1 | P0 |
| PR-16 Error contract | §6.1, §14 rule 8 | P0 |
| PR-18 Panel + onboarding | D-11, §11 | P0 |
| PR-11 Scenarios | FR-07 | P1 |
| PR-12 Live log + Mock this | FR-09, D-10 | P1 |
| PR-13 Test route | FR-10 | P1 |
| PR-14 Export/import | FR-12 | P1 |
| PR-17 Operability | §12.2, §12.3 | P1 |
| PR-19 Templated bodies | §7.3 Phase 2 | P1 |
| PR-20 … PR-25 | §7.3 Phase 3, §12.4, OQ-01 | P2 |
| C-01 Markdown, agent-friendly docs | §0, §14 | Constraint (all phases) |
