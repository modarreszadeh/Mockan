/** A stand-in for `WebSocket` so tests can push messages through the live-log hook (D-19). */
import { vi } from "vitest"

export class FakeSocket {
  static instances: FakeSocket[] = []
  onopen: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  closed = false
  readonly url: string

  constructor(url: string) {
    this.url = url
    FakeSocket.instances.push(this)
  }

  close() {
    this.closed = true
  }

  /** What the server does. */
  open() {
    this.onopen?.()
  }
  send(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) })
  }
  drop() {
    this.onclose?.()
  }
}

export function installFakeSocket() {
  FakeSocket.instances = []
  vi.stubGlobal("WebSocket", FakeSocket)
  return {
    /** The most recent connection. */
    get current() {
      return FakeSocket.instances.at(-1)
    },
    all: () => FakeSocket.instances,
  }
}
