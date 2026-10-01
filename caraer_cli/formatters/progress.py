"""Visible progress for initialization, including redirected terminal output."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from threading import Event, Thread
from time import monotonic

from rich.console import Console
from rich.text import Text

console = Console(stderr=True)


@contextmanager
def progress_step(label: str, *, interval: float = 5.0) -> Iterator[None]:
    """Report a stage immediately and periodically until it finishes."""
    started = monotonic()
    stopped = Event()
    console.print(Text(f"… {label}", style="cyan"))

    def report_wait() -> None:
        while not stopped.wait(interval):
            elapsed = int(monotonic() - started)
            console.print(Text(f"… {label} — still working ({elapsed}s elapsed)", style="dim"))

    reporter = Thread(target=report_wait, daemon=True)
    reporter.start()
    try:
        yield
    finally:
        stopped.set()
        reporter.join()
    console.print(Text(f"✓ {label} ({monotonic() - started:.1f}s)", style="green"))
