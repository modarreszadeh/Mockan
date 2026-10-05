/**
 * The Monaco editor itself, loaded lazily by JsonEditor. Monaco is bundled from the local
 * `monaco-editor` package (no CDN — the Panel runs on the internal network, NFR-05).
 * Theme colours are read from the CSS tokens at runtime, so no colour is hard-coded here.
 */
import Editor, { loader } from "@monaco-editor/react"
import * as monaco from "monaco-editor/editor/editor.api"
import "monaco-editor/language/json/monaco.contribution"
import EditorWorker from "monaco-editor/editor/editor.worker?worker"
import JsonWorker from "monaco-editor/language/json/json.worker?worker"

self.MonacoEnvironment = {
  getWorker: (_workerId: string, label: string) => (label === "json" ? new JsonWorker() : new EditorWorker()),
}
loader.config({ monaco })

const THEME = "mockan-dark"
let themeDefined = false

function defineTheme() {
  if (themeDefined) return
  const style = getComputedStyle(document.documentElement)
  const token = (name: string) => style.getPropertyValue(name).trim()
  const bare = (name: string) => token(name).replace("#", "")
  monaco.editor.defineTheme(THEME, {
    base: "vs-dark",
    inherit: true,
    rules: [
      { token: "string.key.json", foreground: bare("--accent-amber") },
      { token: "string.value.json", foreground: bare("--accent-teal") },
      { token: "number.json", foreground: bare("--on-dark") },
      { token: "keyword.json", foreground: bare("--primary") },
      { token: "delimiter", foreground: bare("--on-dark-soft") },
    ],
    colors: {
      "editor.background": token("--surface-dark-soft"),
      "editor.foreground": token("--on-dark"),
      "editorLineNumber.foreground": token("--muted-soft"),
      "editorLineNumber.activeForeground": token("--on-dark-soft"),
      "editor.lineHighlightBackground": token("--surface-dark-elevated"),
      "editorCursor.foreground": token("--primary"),
      "editor.selectionBackground": `${token("--on-dark-soft")}55`,
      "editorGutter.background": token("--surface-dark-soft"),
    },
  })
  themeDefined = true
}

export interface MonacoSurfaceProps {
  id: string
  value: string
  onChange: (value: string) => void
  onBlur?: () => void
  label: string
  height: number
  describedBy?: string
}

export default function MonacoSurface({ id, value, onChange, onBlur, label, height, describedBy }: MonacoSurfaceProps) {
  return (
    <div id={id} data-testid="json-editor" aria-describedby={describedBy}>
      <Editor
        height={height}
        language="json"
        theme={THEME}
        value={value}
        beforeMount={defineTheme}
        onChange={(next) => onChange(next ?? "")}
        onMount={(editor) => {
          editor.onDidBlurEditorText(() => onBlur?.())
        }}
        loading={<div className="bg-surface-dark-soft" style={{ height }} />}
        options={{
          ariaLabel: label,
          fontFamily: "'JetBrains Mono', ui-monospace, monospace",
          fontSize: 13,
          lineHeight: 20,
          minimap: { enabled: false },
          scrollBeyondLastLine: false,
          automaticLayout: true,
          tabSize: 2,
          wordWrap: "off",
          renderLineHighlight: "line",
          padding: { top: 12, bottom: 12 },
          fixedOverflowWidgets: true,
        }}
      />
    </div>
  )
}
