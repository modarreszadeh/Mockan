import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Slider } from "@/components/ui/slider"
import { DELAY_PRESETS } from "@/lib/http"
import { MAX_DELAY_MS } from "@/lib/validation"

export interface DelayFieldProps {
  id: string
  value: number
  onChange: (value: number) => void
  onBlur: () => void
  invalid: boolean
  describedBy?: string
}

/** Artificial delay 0–30 000 ms (US-12): slider + number input + presets. */
export function DelayField({ id, value, onChange, onBlur, invalid, describedBy }: DelayFieldProps) {
  const safe = Number.isFinite(value) ? Math.min(Math.max(value, 0), MAX_DELAY_MS) : 0
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <Slider
          className="min-w-40 flex-1"
          min={0}
          max={MAX_DELAY_MS}
          step={100}
          value={[safe]}
          onValueChange={([next]) => onChange(next ?? 0)}
          aria-label="Delay slider"
        />
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
          <span className="text-muted-foreground">ms</span>
        </div>
      </div>
      <div className="flex flex-wrap gap-2" role="group" aria-label="Delay presets">
        {DELAY_PRESETS.map((preset) => (
          <Button
            key={preset.ms}
            type="button"
            size="sm"
            variant={value === preset.ms ? "secondary" : "outline"}
            aria-pressed={value === preset.ms}
            onClick={() => onChange(preset.ms)}
          >
            {preset.label}
          </Button>
        ))}
      </div>
    </div>
  )
}
