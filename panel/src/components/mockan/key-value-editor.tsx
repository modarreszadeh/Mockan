import { PlusIcon, XIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import type { KeyValueRow } from "@/lib/validation"
import { cn } from "@/lib/utils"

export interface KeyValueEditorProps {
  rows: KeyValueRow[]
  onChange: (rows: KeyValueRow[]) => void
  /** Accessible name prefix and column header, e.g. "Header name". */
  keyLabel: string
  valueLabel?: string
  addLabel: string
  /** Conditions allow `equals` or `exists` (value hidden for `exists`); headers are always `equals`. */
  allowExists?: boolean
  keyPlaceholder?: string
  valuePlaceholder?: string
  errors?: ({ key?: string; value?: string } | undefined)[]
  emptyText?: string
  className?: string
}

/** Rows of key / operator / value, used for headers, query conditions and header conditions. */
export function KeyValueEditor({
  rows,
  onChange,
  keyLabel,
  valueLabel = "Value",
  addLabel,
  allowExists,
  keyPlaceholder,
  valuePlaceholder,
  errors,
  emptyText = "None yet.",
  className,
}: KeyValueEditorProps) {
  const update = (index: number, patch: Partial<KeyValueRow>) =>
    onChange(rows.map((row, i) => (i === index ? { ...row, ...patch } : row)))
  const remove = (index: number) => onChange(rows.filter((_, i) => i !== index))
  const add = () => onChange([...rows, { key: "", operator: "equals", value: "" }])

  return (
    <div className={cn("space-y-2", className)}>
      {rows.length === 0 ? <p className="text-muted-foreground">{emptyText}</p> : null}
      {rows.map((row, index) => {
        const error = errors?.[index]
        const n = index + 1
        return (
          <div key={index} className="space-y-1">
            <div
              className={cn(
                "grid items-start gap-2",
                allowExists
                  ? "grid-cols-[1fr_auto] sm:grid-cols-[1fr_8rem_1fr_auto]"
                  : "grid-cols-[1fr_auto] sm:grid-cols-[1fr_1fr_auto]",
              )}
            >
              <Input
                aria-label={`${keyLabel} ${n}`}
                aria-invalid={Boolean(error?.key) || undefined}
                className="font-mono text-[13px]"
                placeholder={keyPlaceholder}
                value={row.key}
                onChange={(e) => update(index, { key: e.target.value })}
              />
              {allowExists ? (
                <Select
                  value={row.operator}
                  onValueChange={(operator) =>
                    update(index, {
                      operator: operator as KeyValueRow["operator"],
                      value: operator === "exists" ? "" : row.value,
                    })
                  }
                >
                  <SelectTrigger aria-label={`Operator ${n}`} className="order-3 w-full sm:order-none">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="equals">equals</SelectItem>
                    <SelectItem value="exists">exists</SelectItem>
                  </SelectContent>
                </Select>
              ) : null}
              {row.operator === "exists" ? (
                <span className="order-4 hidden sm:order-none sm:block" />
              ) : (
                <Input
                  aria-label={`${valueLabel} ${n}`}
                  aria-invalid={Boolean(error?.value) || undefined}
                  className="order-4 col-span-1 font-mono text-[13px] sm:order-none"
                  placeholder={valuePlaceholder}
                  value={row.value}
                  onChange={(e) => update(index, { value: e.target.value })}
                />
              )}
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="order-2 sm:order-none"
                aria-label={`Remove ${keyLabel.toLowerCase()} ${n}`}
                onClick={() => remove(index)}
              >
                <XIcon aria-hidden />
              </Button>
            </div>
            {error?.key || error?.value ? <p className="text-[13px] text-error">{error.key ?? error.value}</p> : null}
          </div>
        )
      })}
      <Button type="button" variant="outline" size="sm" onClick={add}>
        <PlusIcon aria-hidden />
        {addLabel}
      </Button>
    </div>
  )
}
