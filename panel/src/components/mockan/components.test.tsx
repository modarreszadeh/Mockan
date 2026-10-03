import { fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { InboxIcon } from "lucide-react"
import { useState } from "react"
import { describe, expect, it } from "vitest"

import { ApiError } from "@/api/client"
import type { KeyValueRow } from "@/lib/validation"
import { axe } from "@/test/render"

import {
  BaseUrlCard,
  EmptyState,
  EnvBadge,
  JsonEditor,
  KeyValueEditor,
  MethodBadge,
  PatternText,
  ProblemAlert,
  SourceBadge,
  StatusCode,
} from "."

describe("BaseUrlCard", () => {
  it("PR-18 copies the .env line with one click and confirms", async () => {
    const user = userEvent.setup()
    const { container } = render(<BaseUrlCard slug="ehtesham" />)
    expect(screen.getByTestId("env-line")).toHaveTextContent("VITE_API_BASE_URL=https://mock.novin-tools.com/ehtesham")
    await user.click(screen.getByRole("button", { name: "Copy .env line" }))
    expect(await screen.findByRole("button", { name: "Copied .env line" })).toHaveTextContent("Copied")
    expect(await axe(container)).toHaveNoViolations()
  })
})

describe("badges", () => {
  it("always carry text, not only colour", () => {
    render(
      <>
        <MethodBadge method="DELETE" />
        <SourceBadge source="Mocked" />
        <StatusCode code={503} />
        <EnvBadge environment="dev" isOverride />
      </>,
    )
    expect(screen.getByText("DELETE")).toBeInTheDocument()
    expect(screen.getByText("Mocked")).toBeInTheDocument()
    expect(screen.getByText("503")).toBeInTheDocument()
    expect(screen.getByText("(not the Service default)")).toBeInTheDocument()
  })
})

describe("PatternText", () => {
  it("highlights template params", () => {
    render(<PatternText pattern="/orders/{id}/files/{*rest}" matchType="Template" />)
    expect(screen.getByText("{id}")).toHaveClass("text-primary-active")
    expect(screen.getByText("{*rest}")).toHaveClass("text-primary-active")
  })
})

function JsonHarness({ initial }: { initial: string }) {
  const [value, setValue] = useState(initial)
  return <JsonEditor id="body" label="Response body" value={value} onChange={setValue} />
}

describe("JsonEditor", () => {
  it("PR-06 shows Line X, Col Y for invalid JSON and formats valid JSON", async () => {
    render(<JsonHarness initial={'{"a":1,}'} />)
    const editor = await screen.findByLabelText("Response body")
    expect(screen.getByRole("status")).toHaveTextContent(/^Line 1, Col 8:/)
    expect(screen.getByRole("button", { name: "Format" })).toBeDisabled()
    fireEvent.change(editor, { target: { value: '{"a":1}' } })
    expect(screen.queryByRole("status")).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Format" }))
    expect(editor).toHaveValue('{\n  "a": 1\n}')
    expect(screen.getByTestId("json-size")).toHaveTextContent("12 B / 1 MB")
  })
})

function KvHarness() {
  const [rows, setRows] = useState<KeyValueRow[]>([{ key: "X-Feature", operator: "exists", value: "" }])
  return (
    <KeyValueEditor rows={rows} onChange={setRows} allowExists keyLabel="Header name" addLabel="Add header condition" />
  )
}

describe("KeyValueEditor", () => {
  it("hides the value for exists and adds/removes rows", async () => {
    const user = userEvent.setup()
    const { container } = render(<KvHarness />)
    expect(screen.queryByLabelText("Value 1")).not.toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Add header condition" }))
    expect(screen.getByLabelText("Value 2")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Remove header name 1" }))
    expect(screen.getAllByLabelText(/Header name/)).toHaveLength(1)
    expect(await axe(container)).toHaveNoViolations()
  })
})

describe("EmptyState and ProblemAlert", () => {
  it("render title, copy and code", async () => {
    const { container } = render(
      <>
        <EmptyState icon={InboxIcon} title="No rules yet" description="All traffic is proxied." />
        <ProblemAlert
          error={new ApiError(502, { title: "Unreachable", code: "upstream_unreachable" })}
          onRetry={() => undefined}
        />
      </>,
    )
    expect(screen.getByRole("heading", { name: "No rules yet" })).toBeInTheDocument()
    expect(screen.getByText("upstream_unreachable")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
  })
})
