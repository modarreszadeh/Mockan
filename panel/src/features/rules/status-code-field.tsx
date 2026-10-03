import { ChevronDownIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { Input } from "@/components/ui/input"
import { reasonPhrase, STATUS_PRESETS } from "@/lib/http"

export interface StatusCodeFieldProps {
  id: string
  value: number
  onChange: (value: number) => void
  onBlur: () => void
  invalid: boolean
  describedBy?: string
}

/** Status code combobox: free numeric entry (100–599) plus a menu of common codes. */
export function StatusCodeField({ id, value, onChange, onBlur, invalid, describedBy }: StatusCodeFieldProps) {
  return (
    <div className="flex items-center gap-2">
      <Input
        id={id}
        inputMode="numeric"
        className="w-24 font-mono"
        value={Number.isNaN(value) ? "" : String(value)}
        onChange={(e) => onChange(e.target.value === "" ? Number.NaN : Number(e.target.value))}
        onBlur={onBlur}
        aria-invalid={invalid || undefined}
        aria-describedby={describedBy}
      />
      <span className="min-w-0 truncate text-muted-foreground">{reasonPhrase(value)}</span>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button type="button" variant="outline" size="sm" className="ml-auto">
            Common codes
            <ChevronDownIcon aria-hidden />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="max-h-80 min-w-56">
          {STATUS_PRESETS.map((code) => (
            <DropdownMenuItem key={code} onSelect={() => onChange(code)} className="gap-3">
              <span className="font-mono">{code}</span>
              <span className="text-muted-foreground">{reasonPhrase(code)}</span>
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )
}
