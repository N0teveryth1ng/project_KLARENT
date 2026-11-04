import asyncio
from app.recovery.retry_manager import RetryManager


def test_retryable_failure_triggers_retry():
    rm = RetryManager(max_retries=2, backoff_base=1)
    attempts = []
    
    async def failing_func():
        attempts.append(1)
        raise Exception("network timeout")
    
    try:
        asyncio.get_event_loop().run_until_complete(rm.retry_with_backoff(failing_func))
    except Exception:
        pass
    
    assert len(attempts) == 3  # initial + 2 retries


def test_non_retryable_failure_does_not_trigger_retry():
    rm = RetryManager(max_retries=3, backoff_base=1)
    attempts = []
    
    async def failing_func():
        attempts.append(1)
        raise Exception("invalid credentials")
    
    try:
        asyncio.get_event_loop().run_until_complete(rm.retry_with_backoff(failing_func))
    except Exception:
        pass
    
    assert len(attempts) == 1  # No retries
