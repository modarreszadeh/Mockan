/** Every Admin API route the Panel calls (arch §10), backed by the in-memory db. */
import { authHandlers } from "./auth"
import { logHandlers } from "./logs"
import { meHandlers } from "./me"
import { ruleHandlers } from "./rules"
import { serviceHandlers } from "./services"
import { testRouteHandlers } from "./test-route"
import { transferHandlers } from "./transfer"

// `rules/export` and `rules/import` go before `rules/:ruleId`, which would otherwise take them.
export const handlers = [
  ...authHandlers,
  ...meHandlers,
  ...serviceHandlers,
  ...transferHandlers,
  ...ruleHandlers,
  ...logHandlers,
  ...testRouteHandlers,
]
