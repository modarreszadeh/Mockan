# Mockan

Mockan lets a frontend Developer answer chosen requests with mock responses while every other request goes to the real backend. This file is the project glossary and nothing else; the system design is in [`docs/agent/mockan-architecture.md`](docs/agent/mockan-architecture.md) and the product intent in [`docs/product/mockan-prd.md`](docs/product/mockan-prd.md).

## Language

### Mocking

**MockRule**:
A Developer-owned rule: when a request matches it, Mockan answers with the rule's active scenario instead of forwarding the request.
_Avoid_: Endpoint mock, route mock

**Scenario**:
A named variant of the response a MockRule returns (for example `success`, `empty`, `error-500`). A rule has one or more scenarios; the architecture's `MockResponse` is the same thing.
_Avoid_: Response variant, mode

**Active scenario**:
The one scenario of a rule that is served when the rule matches. Every rule always has exactly one. It is independent of whether the rule is enabled: a disabled rule keeps its active scenario, it is just never served.
_Avoid_: Live scenario, current scenario, selected scenario (the scenario being edited in the Panel is a different thing)

**Enabled / disabled rule**:
Whether a MockRule takes part in matching at all. A disabled rule is skipped and its requests are forwarded to the real backend.
_Avoid_: Active rule, live rule, on/off

**Duplicate (a scenario)**:
Create a new scenario of the same rule as a copy of an existing one, to be changed afterwards. Scenarios are made this way, not from blank.
_Avoid_: Add scenario, clone

### Observing

**Request log**:
The recent requests that passed through a Developer's base URL, each with its outcome: Proxied, Mocked or Error.
_Avoid_: History, traffic, audit log (the audit log records configuration changes, not requests)

**Live log**:
The Panel's view of the request log that shows new requests as they arrive. "Live" belongs to this view and its connection state only.
_Avoid_: Using "live" for scenarios or rules

**Mock this**:
Turn a logged Proxied or Error request into an Exact MockRule that returns the response that was logged. Not offered for a Mocked request, because a rule already answers it.
_Avoid_: Record, capture

**Test route**:
Ask what would happen to a given request (mocked by which rule, proxied to which upstream, or an error) without sending it.
_Avoid_: Dry run, simulate
