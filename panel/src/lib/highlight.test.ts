import { describe, expect, it } from "vitest"

import { detectBodyLanguage, tokenize } from "./highlight"

const kinds = (code: string, language: Parameters<typeof tokenize>[1]) =>
  tokenize(code, language)
    .filter((t) => t.kind !== "plain")
    .map((t) => `${t.kind}:${t.text}`)

describe("tokenize", () => {
  it("splits JSON into keys, strings, numbers, keywords and punctuation", () => {
    expect(kinds('{"a": "x", "n": -1.5e2, "ok": true, "z": null}', "json")).toEqual([
      "punctuation:{",
      'key:"a"',
      "punctuation::",
      'string:"x"',
      "punctuation:,",
      'key:"n"',
      "punctuation::",
      "number:-1.5e2",
      "punctuation:,",
      'key:"ok"',
      "punctuation::",
      "keyword:true",
      "punctuation:,",
      'key:"z"',
      "punctuation::",
      "keyword:null",
      "punctuation:}",
    ])
  })

  it("keeps a cut-off JSON sample intact", () => {
    const code = '{"a": "long text that was trunc'
    expect(
      tokenize(code, "json")
        .map((t) => t.text)
        .join(""),
    ).toBe(code)
  })

  it("colours HTTP status and header lines", () => {
    expect(kinds("HTTP/1.1 200 OK\nContent-Type: application/json", "http")).toEqual([
      "keyword:HTTP/1.1",
      "number:200",
      "key:Content-Type",
      "punctuation:: ",
      "string:application/json",
    ])
  })

  it("colours .env lines and leaves plain text alone", () => {
    expect(kinds("VITE_API_BASE_URL=https://x/y", "env")).toEqual([
      "key:VITE_API_BASE_URL",
      "punctuation:=",
      "string:https://x/y",
    ])
    expect(tokenize("hello", "text")).toEqual([{ text: "hello", kind: "plain" }])
  })
})

describe("detectBodyLanguage", () => {
  it("treats objects and arrays as json", () => {
    expect(detectBodyLanguage(' {"a":1}')).toBe("json")
    expect(detectBodyLanguage("[1,2")).toBe("json")
    expect(detectBodyLanguage("<html>")).toBe("text")
  })
})
