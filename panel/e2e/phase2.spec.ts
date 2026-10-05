/**
 * Phase 2 (M5) against the MSW dev backend: a request arrives in the live log over the simulated hub, "Mock this"
 * turns it into a rule, a duplicated scenario is made active, Test route confirms it, and the rules are exported.
 */
import { expect, test } from "@playwright/test"

test("Phase 2: live log → Mock this → scenarios → Test route → export", async ({ page }) => {
  await page.goto("/logs?mswScenario=default")
  await expect(page.getByRole("heading", { name: "Live log" })).toBeVisible()
  await expect(page.getByRole("status").filter({ hasText: "Live" })).toBeVisible()

  // The simulated hub pushes a request every few seconds; the list grows without a reload.
  const rows = page.getByRole("row")
  const before = await rows.count()
  await expect.poll(async () => rows.count(), { timeout: 15_000 }).toBeGreaterThan(before)

  // Mock this on a logged request opens the new rule.
  await page.getByRole("button", { name: "Details of GET /limsa/api/v1/orders/4211" }).click()
  const details = page.getByRole("dialog")
  await expect(details.getByRole("region", { name: "Request headers" })).toContainText("authorization: ***")
  await details.getByRole("button", { name: "Mock this" }).click()
  await expect(page).toHaveURL(/\/rules\/[0-9a-f-]+$/)
  await expect(page.getByLabel("Pattern", { exact: true })).toHaveValue("/limsa/api/v1/orders/4211")

  // Duplicate the scenario, make the copy active.
  await page.getByRole("button", { name: "Duplicate scenario" }).click()
  await expect(page.getByRole("tab", { selected: true })).toContainText("-copy")
  await page.getByLabel("Status code").fill("503")
  await page.getByRole("button", { name: "Save" }).click()
  await expect(page.getByText("All changes saved")).toBeVisible()
  await page.getByRole("button", { name: "Make active" }).click()
  await expect(page.getByText("The Gateway serves this scenario.")).toBeVisible()

  // Test route says that request would now be answered by the mock.
  await page.getByRole("link", { name: "Test route" }).click()
  await page.getByLabel("Path").fill("/limsa/api/v1/orders/4211")
  await page.getByRole("button", { name: "Test route" }).click()
  await expect(page.getByTestId("outcome-reason")).toContainText("won with priority")
  await expect(page.getByText("503")).toBeVisible()

  // Export downloads a JSON file.
  await page.getByRole("link", { name: "Rules", exact: true }).click()
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "Export" }).click(),
  ])
  expect(download.suggestedFilename()).toMatch(/^mockan-rules-ehtesham-\d{4}-\d{2}-\d{2}\.json$/)
})
