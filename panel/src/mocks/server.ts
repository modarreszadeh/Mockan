/** MSW for Vitest (Node). Tests call `resetDb(scenario)` in `beforeEach` via src/test/setup.ts. */
import { setupServer } from "msw/node"

import { handlers } from "./handlers"

export const server = setupServer(...handlers)
