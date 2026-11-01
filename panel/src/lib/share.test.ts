import { describe, expect, it } from "vitest"

import { shareUrl } from "./share"

describe("shareUrl", () => {
  it("S-6 builds the public page address from the Panel's origin and base path", () => {
    expect(shareUrl("abc_DEF-123", "https://mock.test")).toBe("https://mock.test/shared/abc_DEF-123")
  })

  it("defaults to the current origin", () => {
    expect(shareUrl("tok")).toBe(`${window.location.origin}/shared/tok`)
  })
})
