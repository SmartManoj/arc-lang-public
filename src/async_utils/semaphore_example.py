"""
Example of using MonitoredSemaphore with dynamic limit updates.

This example demonstrates how the semaphores fetch their limits from the Railway endpoints.
"""

import asyncio
import os
from src.async_utils.semaphore_monitor import MonitoredSemaphore


async def test_semaphore_with_url():
    """Test the MonitoredSemaphore with the actual Railway URLs."""
    
    print("Testing MonitoredSemaphore with dynamic limit updates...")
    print("=" * 60)
    
    # Test API semaphore
    api_semaphore = MonitoredSemaphore(
        value=10,  # Initial limit
        name="test_api_semaphore",
        update_url="https://jj-production.up.railway.app/api_semaphore/concurrency_limit",
        update_interval=5,  # Short interval for testing
    )
    
    # Test tasks semaphore
    tasks_semaphore = MonitoredSemaphore(
        value=5,  # Initial limit
        name="test_tasks_semaphore", 
        update_url="https://jj-production.up.railway.app/tasks_semaphore/concurrency_limit",
        update_interval=5,  # Short interval for testing
    )
    
    print(f"API Semaphore initial limit: {api_semaphore.current_limit}")
    print(f"Tasks Semaphore initial limit: {tasks_semaphore.current_limit}")
    print("\nWaiting 10 seconds to see if limits update from URLs...")
    print("(The semaphores will check for updates every 5 seconds)")
    
    # Simulate some work to see the semaphore in action
    async def do_work(semaphore, task_id: int, task_type: str):
        async with semaphore:
            print(f"[{task_type}] Task {task_id} started - Active: {semaphore.active_count}/{semaphore.current_limit}")
            await asyncio.sleep(1)  # Simulate work
            print(f"[{task_type}] Task {task_id} completed")
    
    # Create some tasks for both semaphores
    api_tasks = []
    tasks_tasks = []
    
    # Start some work with both semaphores
    for i in range(3):
        api_tasks.append(asyncio.create_task(do_work(api_semaphore, i, "API")))
        tasks_tasks.append(asyncio.create_task(do_work(tasks_semaphore, i, "TASKS")))
        await asyncio.sleep(0.2)
    
    # Wait a bit to see if limits update
    await asyncio.sleep(10)
    
    print("\n" + "=" * 60)
    print(f"API Semaphore current limit: {api_semaphore.current_limit}")
    print(f"Tasks Semaphore current limit: {tasks_semaphore.current_limit}")
    print("=" * 60)
    
    # Wait for all tasks to complete
    await asyncio.gather(*api_tasks, *tasks_tasks)
    
    # Cancel the update tasks
    api_semaphore._update_task.cancel()
    tasks_semaphore._update_task.cancel()
    
    try:
        await api_semaphore._update_task
        await tasks_semaphore._update_task
    except asyncio.CancelledError:
        pass


async def test_manual_update():
    """Test manual semaphore limit updates."""
    print("\n\nTesting manual limit updates...")
    print("=" * 60)
    
    semaphore = MonitoredSemaphore(
        value=5,
        name="manual_test_semaphore",
        update_url="https://jj-production.up.railway.app/api_semaphore/concurrency_limit",
        update_interval=60,  # Long interval since we'll update manually
    )
    
    print(f"Initial limit: {semaphore.current_limit}")
    print(f"Active requests: {semaphore.active_count}")
    print(f"Available permits: {semaphore.available_permits}")
    
    # Manually update the limit
    print("\nManually updating limit to 15...")
    await semaphore.update_limit(15)
    
    print(f"New limit: {semaphore.current_limit}")
    print(f"Available permits: {semaphore.available_permits}")
    
    # Cancel the update task
    semaphore._update_task.cancel()
    try:
        await semaphore._update_task
    except asyncio.CancelledError:
        pass


async def main():
    """Run all tests."""
    # Test with actual URLs
    await test_semaphore_with_url()
    
    # Test manual updates
    await test_manual_update()
    
    print("\nAll tests completed!")


if __name__ == "__main__":
    # Set up minimal environment if needed
    if "MAX_CONCURRENCY" not in os.environ:
        os.environ["MAX_CONCURRENCY"] = "100"
    
    asyncio.run(main())