/**
 * Simulated `/hubs/request-log` for the MSW dev backend (browser only): every few seconds a made-up request
 * "arrives" and is pushed to the connected Panel, like the real hub does after the Gateway logs it (D-19).
 */
import { ws } from "msw"

import type { RequestLogEntry } from "@/api/types"

import { appendLog } from "./handlers/logs"

const hub = ws.link("*/hubs/request-log")

const SAMPLES: Pick<RequestLogEntry, "method" | "path" | "source" | "statusCode" | "durationMs">[] = [
  { method: "GET", path: "/limsa/api/v1/orders/4212", source: "Proxied", statusCode: 200, durationMs: 74 },
  { method: "GET", path: "/limsa/api/v1/dashboard", source: "Mocked", statusCode: 200, durationMs: 302 },
  { method: "POST", path: "/identity/connect/token", source: "Proxied", statusCode: 200, durationMs: 133 },
  { method: "GET", path: "/limsa/api/v1/items/9", source: "Mocked", statusCode: 404, durationMs: 2 },
  { method: "GET", path: "/limsa/api/v1/orders", source: "Error", statusCode: 502, durationMs: 5001 },
]

export const liveLogHandlers = [
  hub.addEventListener("connection", ({ client }) => {
    let n = 0
    const timer = setInterval(() => {
      const sample = SAMPLES[n++ % SAMPLES.length]!
      const entry = appendLog({
        ...sample,
        query: "",
        serviceId: null,
        ruleId: null,
        requestHeaders: { accept: "application/json", authorization: "***" },
        responseHeaders: { "content-type": "application/json" },
        requestBodySample: null,
        responseBodySample: null,
      })
      client.send(JSON.stringify(entry))
    }, 4000)
    client.addEventListener("close", () => clearInterval(timer))
  }),
]
