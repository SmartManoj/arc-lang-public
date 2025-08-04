"""
Example of how to use the dynamic semaphore updates in your code.

The semaphores are now configured to automatically fetch their limits from:

1. API Semaphore (in structured.py):
   - URL: https://jj-production.up.railway.app/api_semaphore/concurrency_limit
   - Updates every 60 seconds
   - Controls concurrent API calls to LLMs

2. Tasks Semaphore (in run.py):
   - URL: https://jj-production.up.railway.app/tasks_semaphore/concurrency_limit
   - Updates every 60 seconds
   - Controls concurrent challenge solving tasks

The endpoints should return JSON in this format:
{
    "limit": 50
}

If the fetch fails, the semaphore will keep using the last successful value.

You can also manually update limits if needed:
```python
# Manually update a semaphore limit
await API_SEMAPHORE.update_limit(75)
```

To check current status:
```python
print(f"Current limit: {API_SEMAPHORE.current_limit}")
print(f"Active requests: {API_SEMAPHORE.active_count}")
print(f"Available permits: {API_SEMAPHORE.available_permits}")
print(f"Saturation: {API_SEMAPHORE.saturation_percentage}%")
```
"""