"""Sample the process's resident memory while a transfer runs (NFR-04: streaming stays bounded)."""

import os
import threading
import time
from types import TracebackType

PAGE_SIZE = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 4096
STATM = "/proc/self/statm"


def rss_supported() -> bool:
    return os.path.exists(STATM)


def current_rss() -> int:
    """Resident set size of this process, in bytes (Linux)."""
    with open(STATM) as handle:
        return int(handle.read().split()[1]) * PAGE_SIZE


class RssSampler:
    """Context manager: the peak RSS growth over its body, sampled every few milliseconds."""

    def __init__(self, interval: float = 0.005) -> None:
        self._interval = interval
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self.baseline = 0
        self.peak = 0

    @property
    def growth_bytes(self) -> int:
        return max(0, self.peak - self.baseline)

    def _run(self) -> None:
        while not self._stop.is_set():
            self.peak = max(self.peak, current_rss())
            time.sleep(self._interval)

    def __enter__(self) -> RssSampler:
        self.baseline = self.peak = current_rss()
        self._thread.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._stop.set()
        self._thread.join()
        self.peak = max(self.peak, current_rss())
