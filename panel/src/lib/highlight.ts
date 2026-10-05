/** Tiny syntax tokenizer for CodeBlock: JSON bodies, HTTP header blocks and `.env` lines. No dependency, no HTML. */
export type CodeLanguage = "json" | "http" | "env" | "text"

export type TokenKind = "key" | "string" | "number" | "keyword" | "punctuation" | "plain"

export interface Token {
  text: string
  kind: TokenKind
}

/** Language label shown at the top-left of a CodeBlock. */
export const languageLabel: Record<CodeLanguage, string> = {
  json: "json",
  http: "http",
  env: "env",
  text: "text",
}

// A string may be cut off (log samples are truncated), so the closing quote is optional.
const JSON_TOKEN =
  /("(?:\\.|[^"\\\n])*"?)(\s*:)?|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)|\b(true|false|null)\b|([{}[\],:])|(\s+)|([^\s])/g

function tokenizeJson(code: string): Token[] {
  const tokens: Token[] = []
  for (const match of code.matchAll(JSON_TOKEN)) {
    const [text, str, colon, num, keyword, punctuation] = match
    if (str !== undefined) {
      tokens.push({ text: str, kind: colon ? "key" : "string" })
      if (colon) tokens.push({ text: colon, kind: "punctuation" })
    } else if (num !== undefined) tokens.push({ text, kind: "number" })
    else if (keyword !== undefined) tokens.push({ text, kind: "keyword" })
    else if (punctuation !== undefined) tokens.push({ text, kind: "punctuation" })
    else tokens.push({ text, kind: "plain" })
  }
  return tokens
}

const STATUS_LINE = /^(HTTP\/\d(?:\.\d)?)(\s+)(\d{3})(.*)$/
const FIELD_LINE = /^([^\s:=]+)(\s*[:=]\s*)(.*)$/

function tokenizeLines(code: string, language: "http" | "env"): Token[] {
  const tokens: Token[] = []
  code.split("\n").forEach((line, index) => {
    if (index > 0) tokens.push({ text: "\n", kind: "plain" })
    const status = language === "http" ? STATUS_LINE.exec(line) : null
    if (status) {
      const [, version = "", space = "", statusCode = "", reason = ""] = status
      tokens.push(
        { text: version, kind: "keyword" },
        { text: space, kind: "plain" },
        { text: statusCode, kind: "number" },
        { text: reason, kind: "plain" },
      )
      return
    }
    const field = FIELD_LINE.exec(line)
    if (field) {
      const [, name = "", separator = "", value = ""] = field
      tokens.push(
        { text: name, kind: "key" },
        { text: separator, kind: "punctuation" },
        { text: value, kind: "string" },
      )
      return
    }
    if (line) tokens.push({ text: line, kind: "plain" })
  })
  return tokens
}

/** Splits `code` into coloured runs. Concatenating the token texts always gives `code` back. */
export function tokenize(code: string, language: CodeLanguage): Token[] {
  if (language === "json") return tokenizeJson(code)
  if (language === "http" || language === "env") return tokenizeLines(code, language)
  return [{ text: code, kind: "plain" }]
}

/** `json` when the text parses (or looks like a cut-off object/array), otherwise plain `text`. */
export function detectBodyLanguage(sample: string): CodeLanguage {
  return /^\s*[[{]/.test(sample) ? "json" : "text"
}
