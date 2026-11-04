from typing import Dict, Any, Optional
from app.core.logging import logger


class FailureInjector:
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.injected = False
    
    async def inject(self, step_id: str, context: Dict[str, Any] = None) -> bool:
        context = context or {}
        if self.injected:
            return False
        
        failure_config = self.config.get("failure_injection", {})
        if failure_config.get("target_step") == step_id and failure_config.get("occurrence", 1) > 0:
            failure_type = failure_config.get("type")
            logger.warning("Injecting failure", step_id=step_id, failure_type=failure_type)
            self.injected = True
            
            if failure_type == "network_timeout" or failure_type == "lost_response" or failure_type == "lost_response_after_commit":
                raise TimeoutError("Simulated network timeout")
            elif failure_type == "browser_crash":
                raise Exception("Simulated browser crash")
            elif failure_type == "http_500":
                raise Exception("HTTP 500 Internal Server Error")
            elif failure_type == "element_not_found":
                raise Exception("Element not found")
            else:
                raise Exception(f"Injected failure: {failure_type}")
        
        return False
