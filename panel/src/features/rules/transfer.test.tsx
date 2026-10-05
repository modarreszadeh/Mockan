import { screen, waitFor, within } from "@testing-library/react"
import { http, HttpResponse } from "msw"
import { afterEach, describe, expect, it, vi } from "vitest"

import type { RulesExport } from "@/api/types"
import * as download from "@/lib/download"
import { db, resetDb } from "@/mocks/db"
import { server } from "@/mocks/server"
import { axe, renderRoute } from "@/test/render"

import { describeImportErrors, parseImportFile } from "./rules-transfer"

afterEach(() => vi.restoreAllMocks())

const validRule = {
  name: "Imported ping",
  method: "GET",
  matchType: "Exact",
  pattern: "/limsa/ping",
  queryConditions: [],
  headerConditions: [],
  priority: 100,
  isEnabled: true,
  serviceName: "limsa",
  activeResponse: 0,
  responses: [
    {
      name: "ok",
      statusCode: 200,
      headers: {},
      contentType: "application/json",
      body: "{}",
      bodyMode: "Static",
      delayMs: 0,
    },
  ],
}

const fileOf = (content: unknown, name = "rules.json") =>
  new File([typeof content === "string" ? content : JSON.stringify(content)], name, { type: "application/json" })

describe("parseImportFile", () => {
  it("PR-14 accepts a version 1 export and counts rules and scenarios", () => {
    const parsed = parseImportFile(JSON.stringify({ version: 1, rules: [validRule, validRule] }))
    expect(parsed).toMatchObject({ ruleCount: 2, responseCount: 2, names: ["Imported ping", "Imported ping"] })
  })

  it.each([
    ["not JSON", "{oops", /isn't a JSON file/],
    ["an array", "[]", /doesn't look like a Mockan export/],
    ["another version", JSON.stringify({ version: 2, rules: [] }), /Unsupported export version \(2\)/],
    ["no version", JSON.stringify({ rules: [] }), /Unsupported export version \(missing\)/],
    ["no rules key", JSON.stringify({ version: 1 }), /no “rules” list/],
    ["no rules", JSON.stringify({ version: 1, rules: [] }), /contains no rules/],
    ["too many rules", JSON.stringify({ version: 1, rules: Array.from({ length: 201 }, () => ({})) }), /At most 200/],
  ])("rejects %s before calling the server", (_label, text, message) => {
    expect(parseImportFile(text)).toEqual({ error: expect.stringMatching(message) })
  })
})

describe("describeImportErrors", () => {
  it("PR-14 names the rule and the scenario each problem is in", () => {
    expect(
      describeImportErrors(
        {
          "rules.1.pattern": ["Start with /."],
          "rules.0.responses.2.body": ["Line 3: unexpected }"],
          version: ["Bad."],
        },
        ["First", "Second"],
      ),
    ).toEqual([
      "Rule 2 “Second” → pattern: Start with /.",
      "Rule 1 “First” → scenario 3 → body: Line 3: unexpected }",
      "version: Bad.",
    ])
  })
})

describe("Export", () => {
  it("FR-12 downloads the rules as a JSON file and warns about secrets", async () => {
    const save = vi.spyOn(download, "downloadJson").mockImplementation(() => undefined)
    const { user } = renderRoute("/rules")
    await user.click(await screen.findByRole("button", { name: "Export" }))
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1))
    const [filename, data] = save.mock.calls[0]! as [string, RulesExport]
    expect(filename).toMatch(/^mockan-rules-ehtesham-\d{4}-\d{2}-\d{2}\.json$/)
    expect(data.version).toBe(1)
    expect(data.rules).toHaveLength(db.rules.length)
    expect(data.rules[0]).not.toHaveProperty("id")
    expect(await screen.findByText(/Check them for secrets/)).toBeInTheDocument()
  })
})

describe("Import", () => {
  async function openImport(user: ReturnType<typeof renderRoute>["user"]) {
    await user.click(await screen.findByRole("button", { name: "Import" }))
    return await screen.findByRole("dialog", { name: "Import rules" })
  }

  it("PR-14 merge adds the rules and keeps yours (axe clean)", async () => {
    const before = db.rules.length
    const { user } = renderRoute("/rules")
    const dialog = await openImport(user)
    expect(await axe(dialog)).toHaveNoViolations()
    expect(within(dialog).getByRole("button", { name: "Import" })).toBeDisabled()
    await user.upload(within(dialog).getByLabelText("Export file (.json)"), fileOf({ version: 1, rules: [validRule] }))
    expect(await within(dialog).findByTestId("import-summary")).toHaveTextContent("1 rule, 1 scenario")
    await user.click(within(dialog).getByRole("button", { name: "Import" }))
    expect(await screen.findByText(/Imported 1 rule — live in about 2 seconds/)).toBeInTheDocument()
    expect(db.rules).toHaveLength(before + 1)
    expect(db.rules.at(-1)).toMatchObject({ name: "Imported ping" })
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it("PR-14 replace says how many rules it deletes, and does", async () => {
    const before = db.rules.length
    const { user } = renderRoute("/rules")
    const dialog = await openImport(user)
    await user.click(within(dialog).getByRole("radio", { name: /Replace my rules/ }))
    expect(
      within(dialog).getByText(`Deletes your ${before} current rules first, then imports the file.`),
    ).toBeInTheDocument()
    await user.upload(within(dialog).getByLabelText("Export file (.json)"), fileOf({ version: 1, rules: [validRule] }))
    await user.click(await within(dialog).findByRole("button", { name: "Replace and import" }))
    expect(await screen.findByText(/Imported 1 rule, replaced 6 rules/)).toBeInTheDocument()
    expect(db.rules.map((r) => r.name)).toEqual(["Imported ping"])
  })

  it("PR-14 a bad file is explained in the dialog and nothing is sent", async () => {
    let called = false
    server.use(http.post("*/api/v1/me/rules/import", () => ((called = true), HttpResponse.json({}))))
    const { user } = renderRoute("/rules")
    const dialog = await openImport(user)
    await user.upload(within(dialog).getByLabelText("Export file (.json)"), fileOf("not json"))
    expect(await within(dialog).findByText(/isn't a JSON file/)).toBeInTheDocument()
    expect(within(dialog).getByRole("button", { name: "Import" })).toBeDisabled()
    expect(called).toBe(false)
  })

  it("PR-14 all or nothing: every server problem is listed and no rule is created", async () => {
    const before = db.rules.length
    const broken = {
      ...validRule,
      name: "Broken",
      pattern: "no-slash",
      responses: [{ ...validRule.responses[0]!, statusCode: 999 }],
    }
    const { user } = renderRoute("/rules")
    const dialog = await openImport(user)
    await user.upload(
      within(dialog).getByLabelText("Export file (.json)"),
      fileOf({ version: 1, rules: [validRule, broken] }),
    )
    await user.click(await within(dialog).findByRole("button", { name: "Import" }))
    const alert = await within(dialog).findByRole("alert")
    expect(alert).toHaveTextContent("Nothing was imported")
    expect(alert).toHaveTextContent("Rule 2 “Broken” → pattern")
    expect(alert).toHaveTextContent("Rule 2 “Broken” → scenario 1 → statusCode")
    expect(db.rules).toHaveLength(before)
  })

  it("is available from the empty state too", async () => {
    resetDb("empty")
    const { user } = renderRoute("/rules")
    await user.click(await screen.findByRole("button", { name: "Import rules" }))
    expect(await screen.findByRole("dialog", { name: "Import rules" })).toBeInTheDocument()
  })
})
