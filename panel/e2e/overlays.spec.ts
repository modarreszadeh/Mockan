/**
 * Overlay panels (Frontend/plan-responsive-overlays.md): a centered modal at ≥ 768 px (project `chromium`, 1440 × 900),
 * a full-width bottom sheet below (project `mobile`, 390 × 844). Runs in both and checks the geometry.
 */
import { expect, test, type Locator, type Page } from "@playwright/test"

const MODAL_MAX_WIDTH = { sm: 384, md: 576, lg: 672 }

async function expectLayout(page: Page, overlay: Locator, size: keyof typeof MODAL_MAX_WIDTH) {
  await expect(overlay).toBeVisible()
  await page.waitForTimeout(400) // the enter animation
  const box = (await overlay.boundingBox())!
  const viewport = page.viewportSize()!
  if (viewport.width < 768) {
    expect(box.x).toBeCloseTo(0, 0)
    expect(box.width).toBeCloseTo(viewport.width, 0)
    expect(box.y + box.height).toBeCloseTo(viewport.height, 0)
    expect(box.height).toBeLessThanOrEqual(viewport.height * 0.9 + 1)
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(viewport.width)
  } else {
    expect(box.x + box.width / 2).toBeCloseTo(viewport.width / 2, 0)
    expect(box.y + box.height / 2).toBeCloseTo(viewport.height / 2, 0)
    expect(box.width).toBeLessThanOrEqual(MODAL_MAX_WIDTH[size] + 1)
    expect(box.height).toBeLessThanOrEqual(viewport.height * 0.85 + 1)
  }
}

test("OVL-R1/R2 ConfirmDialog (sm)", async ({ page }) => {
  await page.goto("/rules?mswScenario=default")
  await page.getByRole("button", { name: "Disable all" }).click()
  await expectLayout(page, page.getByRole("alertdialog"), "sm")
  await page.getByRole("button", { name: "Cancel" }).click()
  await expect(page.getByRole("alertdialog")).toBeHidden()
})

test("OVL-R1/R2 import rules modal (md)", async ({ page }) => {
  await page.goto("/rules?mswScenario=default")
  await page.getByRole("button", { name: "Import", exact: true }).click()
  await expectLayout(page, page.getByRole("dialog", { name: "Import rules" }), "md")
  await page.keyboard.press("Escape")
  await expect(page.getByRole("dialog")).toBeHidden()
})

test("OVL-R1/R2 Service modal (md) scrolls its body and keeps the footer in view", async ({ page }) => {
  await page.goto("/admin/services?mswScenario=default")
  await page.getByRole("button", { name: "Add Service" }).click()
  const modal = page.getByRole("dialog", { name: "Add a Service" })
  await expectLayout(page, modal, "md")
  const footer = modal.getByRole("button", { name: "Create Service" })
  await expect(footer).toBeInViewport()
  // The body is the one scroll container: the page behind does not scroll.
  expect(await page.evaluate(() => getComputedStyle(document.body).overflow)).not.toBe("visible")
})

test("OVL-R1/R2 log details modal (lg)", async ({ page }) => {
  await page.goto("/logs?mswScenario=default")
  await page.getByRole("button", { name: "Details of GET /limsa/api/v1/orders/4211" }).first().click()
  const modal = page.getByRole("dialog")
  await expectLayout(page, modal, "lg")
  await expect(modal.getByRole("region", { name: "Request headers" })).toContainText("authorization: ***")
  await expect(modal.getByRole("button", { name: "Mock this" })).not.toBeFocused()
  await modal.getByRole("button", { name: "Close" }).click()
  await expect(modal).toBeHidden()
})

test("OVL-R5 resizing across 768 px keeps an open Service form and its values", async ({ page }) => {
  await page.goto("/admin/services?mswScenario=default")
  await page.getByRole("button", { name: "Add Service" }).click()
  const modal = page.getByRole("dialog", { name: "Add a Service" })
  await modal.getByLabel("Name").fill("billing")
  const { width, height } = page.viewportSize()!
  await page.setViewportSize({ width: width >= 768 ? 390 : 1440, height })
  await expect(modal).toBeVisible()
  await expect(modal.getByLabel("Name")).toHaveValue("billing")
  await page.setViewportSize({ width, height })
  await expect(modal.getByLabel("Name")).toHaveValue("billing")
})
