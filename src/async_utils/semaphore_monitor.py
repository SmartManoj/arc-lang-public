import asyncio
from contextlib import asynccontextmanager

from src.logging_unified import debug


class MonitoredSemaphore:
    """Wrapper around asyncio.Semaphore that tracks active requests."""

    def __init__(self, value: int, name: str):
        self._semaphore = asyncio.Semaphore(value)
        self._max_value = value
        self._name = name
        self._active_count = 0

    @property
    def active_count(self):
        """Number of currently active requests."""
        return self._active_count

    @property
    def available_permits(self):
        """Number of available permits."""
        return self._max_value - self._active_count

    @property
    def saturation_percentage(self):
        """Percentage of semaphore saturation (0-100)."""
        return (self._active_count / self._max_value) * 100

    def log_status(self):
        """Log current semaphore status."""
        message = (
            f"Semaphore '{self._name}' status: {self._active_count}/{self._max_value} "
            f"active ({self.saturation_percentage:.1f}% saturated)"
        )
        debug(message)

    @asynccontextmanager
    async def acquire_monitored(self):
        """Acquire semaphore with monitoring."""
        await self._semaphore.acquire()
        self._active_count += 1
        self.log_status()
        try:
            yield
        finally:
            self._active_count -= 1
            self._semaphore.release()
            self.log_status()

    async def __aenter__(self):
        await self._semaphore.acquire()
        self._active_count += 1
        self.log_status()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self._active_count -= 1
        self._semaphore.release()
        self.log_status()
