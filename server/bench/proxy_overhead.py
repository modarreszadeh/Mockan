"""Manual benchmark (not a CI gate): latency direct vs through the Gateway (NFR-01, B4).

The fake upstream and the Gateway each run in their own Uvicorn process (so they don't share a GIL
with the client), a Developer without rules proxies `/svc/...` to the upstream, and the same
requests are sent both ways over keep-alive connections. Target: p95 delta <= 10 ms.

Run from server/:  uv run python bench/proxy_overhead.py [--requests 3000]
"""

import argparse
import asyncio
import os
import socket
import statistics
import subprocess
import sys
import time
from pathlib import Path

import httpx

SERVER_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVER_ROOT))

UPSTREAM_URL_ENV = "BENCH_UPSTREAM_URL"
SLUG = "bench"


def upstream_app():  # type: ignore[no-untyped-def]  # Uvicorn factory
    from tests.support.fake_upstream import UpstreamState, build_fake_upstream

    return build_fake_upstream(UpstreamState())


def gateway_app():  # type: ignore[no-untyped-def]  # Uvicorn factory
    from tests.support.snapshot_builder import SnapshotBuilder

    from mockan.domain.enums import EnvironmentName
    from mockan.gateway.app import create_app
    from mockan.infrastructure.settings import MockanSettings
    from mockan.matching.snapshot import RuleSnapshotProvider

    builder = SnapshotBuilder()
    builder.developer(SLUG)
    builder.service(
        "svc",
        "/svc",
        strip_prefix=True,
        environments={EnvironmentName.STAGE: os.environ[UPSTREAM_URL_ENV]},
    )
    settings = MockanSettings(
        _env_file=None, allowed_upstream_hosts=["127.0.0.1"], log_level="WARNING"
    )
    return create_app(settings, RuleSnapshotProvider(builder.build()))


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def spawn(factory: str, port: int, env: dict[str, str]) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            f"bench.proxy_overhead:{factory}",
            "--factory",
            "--app-dir",
            str(SERVER_ROOT),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
            "--no-access-log",
        ],
        env={**os.environ, **env},
        cwd=SERVER_ROOT,
    )


async def wait_until_up(url: str) -> None:
    async with httpx.AsyncClient(trust_env=False) as client:
        for _ in range(200):
            try:
                await client.get(url)
                return
            except httpx.TransportError:
                await asyncio.sleep(0.05)
    raise RuntimeError(f"{url} did not come up")


async def measure(url: str, requests: int, concurrency: int) -> list[float]:
    """Latency of `requests` GETs (milliseconds), `concurrency` at a time, on keep-alive."""
    limits = httpx.Limits(max_connections=concurrency)
    async with httpx.AsyncClient(trust_env=False, limits=limits) as client:
        for _ in range(200):  # warm-up: connections, imports, caches
            await client.get(url)
        samples: list[float] = []

        async def one() -> None:
            started = time.perf_counter()
            response = await client.get(url)
            samples.append((time.perf_counter() - started) * 1000)
            assert response.status_code == 200

        remaining = requests
        while remaining > 0:
            batch = min(concurrency, remaining)
            await asyncio.gather(*(one() for _ in range(batch)))
            remaining -= batch
        return samples


def p95(samples: list[float]) -> float:
    return sorted(samples)[int(len(samples) * 0.95)]


async def main(requests: int) -> None:
    upstream_port, gateway_port = free_port(), free_port()
    upstream_url = f"http://127.0.0.1:{upstream_port}"
    processes = [
        spawn("upstream_app", upstream_port, {}),
        spawn("gateway_app", gateway_port, {UPSTREAM_URL_ENV: upstream_url}),
    ]
    try:
        await wait_until_up(f"{upstream_url}/status/200")
        await wait_until_up(f"http://127.0.0.1:{gateway_port}/_mockan/health/live")
        print(f"{requests} requests per cell, keep-alive, GET; times in ms")
        print(
            f"{'path':<14}{'conc':>5}  {'direct p50':>10}{'p95':>8}"
            f"  {'gateway p50':>11}{'p95':>8}  {'p95 delta':>9}"
        )
        for path in ("/status/200", "/echo?x=1"):
            for concurrency in (1, 16):
                direct = await measure(f"{upstream_url}{path}", requests, concurrency)
                via = await measure(
                    f"http://127.0.0.1:{gateway_port}/{SLUG}/svc{path}", requests, concurrency
                )
                d50, d95 = statistics.median(direct), p95(direct)
                g50, g95 = statistics.median(via), p95(via)
                verdict = "ok" if g95 - d95 <= 10 else "OVER 10 ms"
                print(
                    f"{path:<14}{concurrency:>5}  {d50:>10.2f}{d95:>8.2f}  {g50:>11.2f}{g95:>8.2f}"
                    f"  {g95 - d95:>9.2f}  {verdict}"
                )
    finally:
        for process in processes:
            process.terminate()
        for process in processes:
            process.wait(timeout=10)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", type=int, default=3000)
    asyncio.run(main(parser.parse_args().requests))
