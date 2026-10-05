/** `POST /me/test-route` (PR-13). */
import { delay, http, HttpResponse } from "msw"

import type { TestRouteRequest } from "@/api/types"

import { db } from "../db"
import { decideRoute } from "../matching"
import { guard } from "../problem"

export const testRouteHandlers = [
  http.post("*/api/v1/me/test-route", async ({ request }) => {
    await delay()
    const stop = guard()
    if (stop) return stop
    return HttpResponse.json(decideRoute(db, (await request.json()) as TestRouteRequest))
  }),
]
