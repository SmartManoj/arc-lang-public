"""
A semaphore implementation that supports immediate limit updates by cancelling excess waiters.
"""
import asyncio
from contextlib import asynccontextmanager
from typing import Optional
import threading
import time
import requests
from collections import deque

import logfire


class CancellableMonitoredSemaphore:
    """Semaphore that can cancel waiting tasks when limit is reduced."""
    
    def __init__(
        self,
        value: int,
        name: str = "",
        update_url: Optional[str] = None,
        update_interval: int = 60,
    ):
        self._max_value = value
        self._name = name
        self._active_count = 0
        self._available = value
        self._waiters = deque()
        self._lock = asyncio.Lock()
        
        # Dynamic update configuration
        self._update_url = update_url
        self._update_interval = update_interval
        self._update_thread = None
        self._last_successful_value = value
        self._stop_event = threading.Event()
        self._loop = None
        
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
        return self._active_count
    
    @property
    def available_permits(self):
        return self._available
    
    @property
    def current_limit(self):
        return self._max_value
    
    @property
    def saturation_percentage(self):
        if self._max_value == 0:
            return 0
        return (self._active_count / self._max_value) * 100
    
    def log_status(self):
        message = (
            f"Semaphore '{self._name}' status: {self._active_count}/{self._max_value} "
            f"active ({self.saturation_percentage:.1f}% saturated)"
        )
        logfire.debug(message)
    
    async def acquire(self):
        """Acquire a permit from the semaphore."""
        async with self._lock:
            if self._available > 0:
                self._available -= 1
                self._active_count += 1
                self.log_status()
                return
        
        # Need to wait
        waiter = asyncio.Future()
        self._waiters.append(waiter)
        try:
            await waiter
            async with self._lock:
                self._active_count += 1
            self.log_status()
        except asyncio.CancelledError:
            # Remove from waiters if still there
            try:
                self._waiters.remove(waiter)
            except ValueError:
                pass
            raise
    
    def release(self):
        """Release a permit back to the semaphore."""
        asyncio.create_task(self._release_async())
    
    async def _release_async(self):
        """Async version of release."""
        async with self._lock:
            self._active_count -= 1
            
            # Wake up a waiter if any
            while self._waiters:
                waiter = self._waiters.popleft()
                if not waiter.done():
                    waiter.set_result(None)
                    self.log_status()
                    return
            
            # No waiters, increase available
            self._available += 1
            self.log_status()
    
    async def update_limit(self, new_limit: int):
        """Update the semaphore limit and cancel excess waiters."""
        if new_limit <= 0:
            raise ValueError("Semaphore limit must be positive")
        
        async with self._lock:
            if new_limit == self._max_value:
                return
            
            old_limit = self._max_value
            self._max_value = new_limit
            
            # Calculate how many permits we should have available
            # available = limit - active
            new_available = new_limit - self._active_count
            
            if new_available < 0:
                # More active than the new limit allows
                self._available = 0
                logfire.warning(
                    f"Semaphore '{self._name}' has {self._active_count} active tasks "
                    f"but new limit is {new_limit}. No new tasks can start until some complete."
                )
            else:
                self._available = new_available
                
                # If we increased the limit, wake up some waiters
                if new_limit > old_limit:
                    to_wake = min(len(self._waiters), new_available)
                    for _ in range(to_wake):
                        if self._waiters:
                            waiter = self._waiters.popleft()
                            if not waiter.done():
                                waiter.set_result(None)
                                self._available -= 1
            
            # If we decreased the limit and have too many waiters, cancel the excess
            if new_limit < old_limit:
                # Calculate how many tasks we can allow total
                allowed_waiting = max(0, new_limit - self._active_count)
                
                # Cancel excess waiters
                while len(self._waiters) > allowed_waiting:
                    waiter = self._waiters.pop()
                    if not waiter.done():
                        waiter.cancel()
            
            logfire.info(
                f"Semaphore '{self._name}' limit updated",
                old_limit=old_limit,
                new_limit=new_limit,
                active_count=self._active_count,
                waiters=len(self._waiters),
            )
            self.log_status()
    
    @asynccontextmanager
    async def acquire_monitored(self):
        """Context manager for acquiring with monitoring."""
        # Capture event loop on first use
        if self._loop is None:
            self._loop = asyncio.get_running_loop()
        
        await self.acquire()
        try:
            yield
        finally:
            self.release()
    
    async def __aenter__(self):
        # Capture event loop on first use
        if self._loop is None:
            self._loop = asyncio.get_running_loop()
        
        await self.acquire()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.release()
    
    def _fetch_limit_from_url(self) -> Optional[int]:
        """Fetch the new limit from the configured URL."""
        try:
            response = requests.get(self._update_url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                limit = data.get("limit")
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
        while not self._stop_event.is_set():
            # Wait for the interval
            for _ in range(self._update_interval):
                if self._stop_event.is_set():
                    return
                time.sleep(1)
            
            new_limit = self._fetch_limit_from_url()
            
            if new_limit is not None and self._loop is not None:
                try:
                    future = asyncio.run_coroutine_threadsafe(
                        self.update_limit(new_limit), self._loop
                    )
                    future.result(timeout=5.0)
                    self._last_successful_value = new_limit
                except Exception as e:
                    logfire.error(
                        f"Failed to update semaphore '{self._name}' limit",
                        error=str(e)
                    )
    
    def stop_updates(self):
        """Stop the update thread."""
        if self._update_thread:
            self._stop_event.set()
            self._update_thread.join(timeout=5)
    
    def __del__(self):
        """Cleanup update thread when object is destroyed."""
        self.stop_updates()