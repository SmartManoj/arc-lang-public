"""Debug script to test MonitoredSemaphore updates."""
import asyncio
import os
import time
from src.async_utils.semaphore_monitor import MonitoredSemaphore


async def debug_semaphore():
    print("Starting semaphore debug test...")
    print("=" * 60)
    
    # Create semaphore with short update interval
    semaphore = MonitoredSemaphore(
        value=10,  # Initial limit
        name="debug_semaphore",
        update_url="https://jj-production.up.railway.app/api_semaphore/concurrency_limit",
        update_interval=3,  # Very short interval for testing
    )
    
    print(f"Initial limit: {semaphore.current_limit}")
    print(f"Update URL: {semaphore._update_url}")
    print(f"Update interval: {semaphore._update_interval} seconds")
    print(f"Update thread alive: {semaphore._update_thread.is_alive() if semaphore._update_thread else 'No thread'}")
    
    # Use the semaphore to capture the event loop
    print("\nUsing semaphore to capture event loop...")
    async with semaphore:
        print("Semaphore acquired and released")
    
    # Wait and check periodically
    for i in range(10):
        await asyncio.sleep(2)
        print(f"\n[{i*2}s] Current limit: {semaphore.current_limit}")
        print(f"     Active count: {semaphore.active_count}")
        print(f"     Thread alive: {semaphore._update_thread.is_alive() if semaphore._update_thread else 'No thread'}")
        
        # Try manual fetch to see if it works
        if i == 3:
            print("\n     Trying manual fetch...")
            result = semaphore._fetch_limit_from_url()
            print(f"     Manual fetch result: {result}")
    
    # Stop the update thread
    semaphore.stop_updates()
    print("\nStopped update thread")


async def test_immediate_update():
    print("\n\nTesting immediate manual update...")
    print("=" * 60)
    
    semaphore = MonitoredSemaphore(
        value=10,
        name="test_immediate",
        update_url="https://jj-production.up.railway.app/api_semaphore/concurrency_limit",
        update_interval=60,
    )
    
    print(f"Initial limit: {semaphore.current_limit}")
    
    # Manually fetch and update
    new_limit = semaphore._fetch_limit_from_url()
    print(f"Fetched limit from URL: {new_limit}")
    
    if new_limit:
        await semaphore.update_limit(new_limit)
        print(f"After manual update: {semaphore.current_limit}")
    
    semaphore.stop_updates()


if __name__ == "__main__":
    # Set up minimal environment if needed
    if "MAX_CONCURRENCY" not in os.environ:
        os.environ["MAX_CONCURRENCY"] = "100"
    
    asyncio.run(debug_semaphore())
    asyncio.run(test_immediate_update())