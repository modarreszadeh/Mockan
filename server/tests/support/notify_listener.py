"""Collect `mockan_config_changed` payloads on a plain asyncpg LISTEN connection."""

import asyncio


class Listener:
    def __init__(self) -> None:
        self.received: list[str] = []

    def __call__(self, _connection: object, _pid: int, _channel: str, payload: str) -> None:
        self.received.append(payload)

    async def payloads(self, expected: int) -> list[str]:
        """Wait (up to 3 s) for `expected` notifications, then pause briefly to catch extras."""
        for _ in range(60):
            if len(self.received) >= expected:
                break
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.2)
        result, self.received = sorted(self.received), []
        return result

    async def nothing(self) -> list[str]:
        await asyncio.sleep(0.4)
        result, self.received = sorted(self.received), []
        return result
