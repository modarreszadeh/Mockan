/**
 * PRD §6 core journey against the MSW dev backend: first login → claim slug → copy base URL → create the Exact
 * rule GET /limsa/api/v1/dashboard with a JSON body → see it in Rules and Overview → disable it → kill switch.
 */
import { expect, test } from "@playwright/test"

const DASHBOARD_JSON = '{"totals": {"samples": 1284, "pending": 37}}'

test("PRD §6 journey: first login to first mock", async ({ page }) => {
  // 1. First login: signed out → simulated SSO → onboarding.
  await page.goto("/?mswScenario=new")
  await expect(page).toHaveURL(/\/onboarding$/)
  await expect(page.getByRole("heading", { name: "Claim your workspace" })).toBeVisible()

  // 2. Claim the slug.
  await page.getByLabel("Workspace slug").fill("ehtesham")
  await page.getByRole("button", { name: /Continue/ }).click()
  await expect(page.getByRole("alertdialog")).toContainText("cannot be changed later")
  await page.getByRole("button", { name: "Claim slug" }).click()

  // 3. Copy the base URL.
  await expect(page.getByTestId("env-line")).toHaveText("VITE_API_BASE_URL=https://mock.novin-tools.com/ehtesham")
  await page.getByRole("button", { name: "Copy .env line" }).click()
  await expect(page.getByRole("button", { name: "Copied .env line" })).toBeVisible()
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(
    "VITE_API_BASE_URL=https://mock.novin-tools.com/ehtesham",
  )

  // 4. Create the Exact rule with the agreed JSON.
  await page.getByRole("link", { name: "Create your first mock" }).click()
  await expect(page).toHaveURL(/\/rules\/new$/)
  await page.getByLabel("Name", { exact: true }).fill("Limsa dashboard")
  await page.getByLabel("Pattern", { exact: true }).fill("/limsa/api/v1/dashboard")
  const editor = page.locator(".monaco-editor").first()
  await editor.click()
  await page.keyboard.insertText(DASHBOARD_JSON)
  await expect(page.getByTestId("rule-sentence")).toContainText("GET requests to /limsa/api/v1/dashboard return 200")
  await page.getByRole("button", { name: "Create rule" }).click()

  // 5. See it in Rules and Overview.
  await expect(page).toHaveURL(/\/rules$/)
  await expect(page.getByRole("link", { name: "Limsa dashboard" })).toBeVisible()
  await expect(page.getByText("Saved — live in about 2 seconds").first()).toBeVisible()
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Overview" }).click()
  await expect(page.getByText("1 mock active · everything else is proxied to the real backend.")).toBeVisible()
  await expect(page.getByRole("region", { name: "Active mocks" })).toContainText("/limsa/api/v1/dashboard")

  // 6. The real endpoint shipped: disable the rule.
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Rules" }).click()
  await page.getByRole("switch", { name: "Disable Limsa dashboard" }).click()
  await expect(page.getByRole("switch", { name: "Enable Limsa dashboard" })).not.toBeChecked()

  // 7. Kill switch on, then off again.
  const killSwitch = page.getByRole("switch", { name: /^Mocks (on|off)$/ })
  await expect(killSwitch).not.toBeChecked()
  await killSwitch.click()
  await expect(page.getByRole("switch", { name: "Mocks on" })).toBeChecked()
  await expect(page.getByRole("switch", { name: "Disable Limsa dashboard" })).toBeChecked()
  await page.getByRole("switch", { name: "Mocks on" }).click()
  await expect(page.getByRole("switch", { name: "Mocks off" })).not.toBeChecked()
  await expect(page.getByRole("switch", { name: "Enable Limsa dashboard" })).not.toBeChecked()
})
