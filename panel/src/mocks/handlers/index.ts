/** Every Admin API route the Panel calls (arch §10), backed by the in-memory db. */
import { authHandlers } from "./auth"
import { meHandlers } from "./me"
import { ruleHandlers } from "./rules"
import { serviceHandlers } from "./services"

export const handlers = [...authHandlers, ...meHandlers, ...serviceHandlers, ...ruleHandlers]
