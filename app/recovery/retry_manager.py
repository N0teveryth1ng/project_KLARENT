import asyncio
from typing import Dict, Any

from app.core.logging import logger


class RetryManager:
    def __init__(self, max_retries: int = 3, backoff_base: int = 2):
        self.max_retries = max_retries
        self.backoff_base = backoff_base
    
    def is_retryable(self, error: Exception) -> bool:
        error_str = str(error).lower()
        retryable_patterns = [
            "timeout",
            "network",
            "connection",
            "500",
            "502",
            "503",
            "504",
            "browser crash",
            "crash"
        ]
        non_retryable_patterns = [
            "invalid credentials",
            "unauthorized",
            "authentication failed",
            "bad request",
            "missing required"
        ]
        
        for pattern in non_retryable_patterns:
            if pattern in error_str:
                return False
        
        for pattern in retryable_patterns:
            if pattern in error_str:
                return True
        
        return False
    
    async def retry_with_backoff(self, func, *args, **kwargs):
        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                result = await func(*args, **kwargs)
                if attempt > 0:
                    logger.info("Retry succeeded", attempt=attempt)
                return result
            except Exception as e:
                last_error = e
                if not self.is_retryable(e):
                    logger.error("Non-retryable error", error=str(e))
                    raise
                if attempt < self.max_retries:
                    wait_time = self.backoff_base ** attempt
                    logger.warning("Retrying after error", attempt=attempt + 1, wait_time=wait_time, error=str(e))
                    await asyncio.sleep(wait_time)
                else:
                    logger.error("Max retries exceeded", error=str(e))
                    raise
        
        raise last_error
