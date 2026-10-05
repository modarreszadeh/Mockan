/** Export button and Import dialog for the Rules screen (PR-14). */
import { DownloadIcon, UploadIcon } from "lucide-react"
import { useRef, useState, type ChangeEvent } from "react"
import { toast } from "sonner"

import { ApiError } from "@/api/client"
import { useMe } from "@/api/queries/me"
import { useExportRules, useImportRules } from "@/api/queries/rules"
import type { ImportMode } from "@/api/types"
import { ProblemAlert } from "@/components/mockan"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { downloadJson } from "@/lib/download"
import { pluralize } from "@/lib/format"
import { cn } from "@/lib/utils"

import { describeImportErrors, parseImportFile, type ParsedImport } from "./rules-transfer"

export function ExportRulesButton({ disabled }: { disabled?: boolean }) {
  const exportRules = useExportRules()
  const me = useMe()
  return (
    <Button
      variant="outline"
      disabled={disabled || exportRules.isPending}
      onClick={() =>
        exportRules.mutate(undefined, {
          onSuccess: (data) => {
            const day = new Date().toISOString().slice(0, 10)
            downloadJson(`mockan-rules-${me.data?.slug ?? "export"}-${day}.json`, data)
            toast.success(`Exported ${pluralize(data.rules.length, "rule")}`, {
              description:
                "Headers and bodies are exported as stored. Check them for secrets before you share the file.",
            })
          },
          onError: () => toast.error("Couldn't export your rules"),
        })
      }
    >
      <DownloadIcon aria-hidden />
      Export
    </Button>
  )
}

const MODES: { value: ImportMode; title: string; hint: string }[] = [
  {
    value: "merge",
    title: "Add to my rules",
    hint: "Keeps your current rules. Importing the same file twice adds the rules twice.",
  },
  { value: "replace", title: "Replace my rules", hint: "Deletes all your current rules first, then imports the file." },
]

const SHOWN_PROBLEMS = 10

export function ImportRulesDialog({
  open,
  onOpenChange,
  existingRuleCount,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  existingRuleCount: number
}) {
  const importRules = useImportRules()
  const input = useRef<HTMLInputElement>(null)
  const [parsed, setParsed] = useState<ParsedImport | null>(null)
  const [fileError, setFileError] = useState<string | null>(null)
  const [fileName, setFileName] = useState<string | null>(null)
  const [mode, setMode] = useState<ImportMode>("merge")

  const reset = () => {
    setParsed(null)
    setFileError(null)
    setFileName(null)
    setMode("merge")
    importRules.reset()
  }

  const onFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    importRules.reset()
    if (!file) return
    setFileName(file.name)
    const result = parseImportFile(await file.text())
    if ("error" in result) {
      setParsed(null)
      setFileError(result.error)
    } else {
      setFileError(null)
      setParsed(result)
    }
  }

  const problems =
    importRules.error instanceof ApiError && Object.keys(importRules.error.fieldErrors).length > 0
      ? describeImportErrors(importRules.error.fieldErrors, parsed?.names ?? [])
      : []

  const submit = () => {
    if (!parsed) return
    importRules.mutate(
      { file: parsed.file, mode },
      {
        onSuccess: (result) => {
          toast.success(
            result.deleted > 0
              ? `Imported ${pluralize(result.created, "rule")}, replaced ${pluralize(result.deleted, "rule")} — live in about 2 seconds`
              : `Imported ${pluralize(result.created, "rule")} — live in about 2 seconds`,
          )
          onOpenChange(false)
          reset()
        },
      },
    )
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next)
        if (!next) reset()
      }}
    >
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Import rules</DialogTitle>
          <DialogDescription className="text-body">
            Choose a file exported from Mockan. It is checked as a whole first: if anything in it is invalid, nothing is
            imported.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <label htmlFor="import-file" className="type-caption text-ink">
              Export file (.json)
            </label>
            <input
              ref={input}
              id="import-file"
              type="file"
              accept="application/json,.json"
              onChange={(event) => void onFile(event)}
              className="block w-full text-[14px] text-body file:mr-3 file:rounded-lg file:border file:bg-canvas file:px-3 file:py-1.5 file:text-ink"
            />
            {fileError ? (
              <p role="alert" className="text-[13px] text-error">
                {fileError}
              </p>
            ) : null}
            {parsed ? (
              <p className="text-[13px] text-body" data-testid="import-summary">
                <span className="font-mono">{fileName}</span>: {pluralize(parsed.ruleCount, "rule")},{" "}
                {pluralize(parsed.responseCount, "scenario")}.
              </p>
            ) : null}
          </div>

          <fieldset className="space-y-2">
            <legend className="type-caption text-ink">What to do with your current rules</legend>
            {MODES.map(({ value, title, hint }) => (
              <label
                key={value}
                className={cn(
                  "flex cursor-pointer items-start gap-3 rounded-xl border p-3 has-checked:border-ink has-focus-visible:ring-3 has-focus-visible:ring-ring/30",
                )}
              >
                <input
                  type="radio"
                  name="import-mode"
                  value={value}
                  checked={mode === value}
                  onChange={() => setMode(value)}
                  className="mt-1 accent-primary"
                />
                <span className="space-y-0.5">
                  <span className="block text-ink">{title}</span>
                  <span className="block text-[13px] text-muted-foreground">
                    {value === "replace" && existingRuleCount > 0
                      ? `Deletes your ${pluralize(existingRuleCount, "current rule")} first, then imports the file.`
                      : hint}
                  </span>
                </span>
              </label>
            ))}
          </fieldset>

          {problems.length > 0 ? (
            <div role="alert" className="space-y-2 rounded-xl border border-error/40 p-4">
              <p className="type-caption text-ink">
                Nothing was imported. Fix {pluralize(problems.length, "problem")} in the file and try again:
              </p>
              <ul className="list-disc space-y-1 pl-5 text-[13px] text-body">
                {problems.slice(0, SHOWN_PROBLEMS).map((line, index) => (
                  <li key={index}>{line}</li>
                ))}
              </ul>
              {problems.length > SHOWN_PROBLEMS ? (
                <p className="text-[13px] text-muted-foreground">and {problems.length - SHOWN_PROBLEMS} more.</p>
              ) : null}
            </div>
          ) : importRules.isError ? (
            <ProblemAlert error={importRules.error} />
          ) : null}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant={mode === "replace" ? "destructive" : "default"}
            disabled={!parsed || importRules.isPending}
            onClick={submit}
          >
            <UploadIcon aria-hidden />
            {importRules.isPending ? "Importing…" : mode === "replace" ? "Replace and import" : "Import"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
