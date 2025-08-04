import asyncio
from contextlib import asynccontextmanager
from typing import Optional
import threading
import time
import requests

import logfire


class MonitoredSemaphore:
    """Wrapper around asyncio.Semaphore that tracks active requests and supports dynamic limits."""

    def __init__(
        self,
        value: int,
        name: str = "",
        update_url: Optional[str] = None,
        update_interval: int = 60,
    ):
        """
        Initialize a monitored semaphore with optional dynamic limit updates.

        Args:
            value: Initial semaphore limit
            name: Name for logging purposes
            update_url: Optional URL to fetch limit updates from (expects { limit: int })
            update_interval: Seconds between update checks (default: 60)
        """
        self._semaphore = asyncio.Semaphore(value)
        self._max_value = value
        self._name = name
        self._active_count = 0
        self._lock = asyncio.Lock()
        # Keep track of old semaphores that are still in use
        self._old_semaphores = []

        # Dynamic update configuration
        self._update_url = update_url
        self._update_interval = update_interval
        self._update_thread = None
        self._last_successful_value = value
        self._stop_event = threading.Event()
        self._loop = None  # Will be set when first used

        # Start update thread if URL is provided
        if self._update_url:
            self._update_thread = threading.Thread(
                target=self._update_loop_thread,
                daemon=True,
                name=f"semaphore_updater_{name}",
            )
            self._update_thread.start()

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
        if self._max_value == 0:
            return 0
        return (self._active_count / self._max_value) * 100

    @property
    def current_limit(self):
        """Current semaphore limit."""
        return self._max_value

    def log_status(self):
        """Log current semaphore status."""
        message = (
            f"Semaphore '{self._name}' status: {self._active_count}/{self._max_value} "
            f"active ({self.saturation_percentage:.1f}% saturated)"
        )
        logfire.debug(message)

    def _fetch_limit_from_url(self) -> Optional[int]:
        """Fetch the new limit from the configured URL (runs in thread)."""
        try:
            print("fetttchicncinc")
            response = requests.get(self._update_url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                print("DATATATAT")
                limit = data.get("limit")
                print("LIMIMITT", limit)
                if isinstance(limit, int) and limit > 0:
                    return limit
        except Exception as e:
            logfire.warning(
                f"Failed to fetch limit update for semaphore '{self._name}'",
                error=str(e),
            )
        return None

    def _update_loop_thread(self):
        """Background thread to periodically update the semaphore limit."""
        print("in update loop")
        while not self._stop_event.is_set():
            # Wait for the interval, but check stop_event periodically
            for _ in range(self._update_interval):
                if self._stop_event.is_set():
                    return
                time.sleep(1)

            new_limit = self._fetch_limit_from_url()

            if new_limit is not None:
                # Schedule the update in the event loop if one is running
                if self._loop is not None:
                    try:
                        print(f"Using captured loop: {self._loop}")
                        future = asyncio.run_coroutine_threadsafe(self.update_limit(new_limit), self._loop)
                        print(f"Scheduled update, future: {future}")
                        # Wait a bit to see the result
                        try:
                            result = future.result(timeout=5.0)
                            print(f"Update completed successfully: {result}")
                        except asyncio.TimeoutError:
                            print(f"Update timed out after 5 seconds!")
                        except Exception as e:
                            print(f"Update failed with error: {type(e).__name__}: {e}")
                        self._last_successful_value = new_limit
                    except Exception as e:
                        print(f"Error scheduling update: {e}")
                        self._last_successful_value = new_limit
                else:
                    # No event loop captured yet
                    print("No event loop captured yet, storing limit for later")
                    self._last_successful_value = new_limit
                    logfire.debug(
                        f"Semaphore '{self._name}' fetched new limit {new_limit} "
                        "(will apply when event loop is available)"
                    )
            else:
                # If fetch failed, keep using the last successful value
                logfire.debug(
                    f"Semaphore '{self._name}' keeping limit at {self._last_successful_value} (fetch failed)"
                )

    async def update_limit(self, new_limit: int):
        """Update the semaphore limit dynamically."""
        print(f"update_limit called with new_limit={new_limit}, current={self._max_value}")
        try:
            if new_limit <= 0:
                raise ValueError("Semaphore limit must be positive")

            print(f"Attempting to acquire lock...")
            async with self._lock:
                print(f"Lock acquired, checking if update needed")
                if new_limit == self._max_value:
                    print(f"No update needed, limit already at {new_limit}")
                    return  # No change needed

                old_limit = self._max_value
                print(f"Update needed: {old_limit} -> {new_limit}, active_count={self._active_count}")

                # Keep the old semaphore to let existing waiters complete
                old_semaphore = self._semaphore
                self._old_semaphores.append(old_semaphore)
                
                # Create a fresh new semaphore with the new limit
                # This will be used for all NEW tasks
                new_semaphore = asyncio.Semaphore(new_limit)
                
                # Update references
                self._semaphore = new_semaphore
                self._max_value = new_limit

                print(f"Successfully updated semaphore limit from {old_limit} to {new_limit}")
                print(f"Created fresh semaphore for new tasks. Old tasks will complete on the previous semaphore.")
                print(f"Active count ({self._active_count}) reflects ALL tasks across all semaphores.")
                
                logfire.info(
                    f"Semaphore '{self._name}' limit updated",
                    old_limit=old_limit,
                    new_limit=new_limit,
                    active_count=self._active_count,
                )
                self.log_status()
        except Exception as e:
            print(f"ERROR in update_limit: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()

    @asynccontextmanager
    async def acquire_monitored(self):
        """Acquire semaphore with monitoring."""
        # Capture the event loop on first use
        if self._loop is None:
            self._loop = asyncio.get_running_loop()
            print(f"Captured event loop on first use: {self._loop}")
        
        await self._semaphore.acquire()
        async with self._lock:
            self._active_count += 1
        self.log_status()
        try:
            yield
        finally:
            async with self._lock:
                self._active_count -= 1
            self._semaphore.release()
            self.log_status()

    async def __aenter__(self):
        # Capture the event loop on first use
        if self._loop is None:
            self._loop = asyncio.get_running_loop()
            print(f"Captured event loop on first use: {self._loop}")
        
        # We must use the current semaphore at the time of acquire
        # This ensures we respect the current limit
        await self._semaphore.acquire()
        
        # Update active count
        async with self._lock:
            self._active_count += 1
        self.log_status()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        async with self._lock:
            self._active_count -= 1
        self._semaphore.release()
        self.log_status()

    def stop_updates(self):
        """Stop the update thread."""
        if self._update_thread:
            self._stop_event.set()
            self._update_thread.join(timeout=5)

    def __del__(self):
        """Cleanup update thread when object is destroyed."""
        self.stop_updates()
