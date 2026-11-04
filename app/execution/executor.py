from typing import Dict, Any
from datetime import datetime

from app.browser.controller import BrowserController
from app.core.logging import logger


class StepExecutor:
    def __init__(self, browser: BrowserController):
        self.browser = browser
    
    async def execute_step(self, step_config: Dict[str, Any]) -> Dict[str, Any]:
        action_type = step_config.get("action_type")
        step_id = step_config.get("step_id")
        
        logger.info("Executing step", step_id=step_id, action_type=action_type)
        
        try:
            if action_type == "navigate":
                await self.browser.navigate(step_config["target"])
                result = {"status": "success"}
            elif action_type == "click":
                await self.browser.page.click(step_config["target"], timeout=step_config.get("timeout", 30000))
                result = {"status": "success"}
            elif action_type == "fill":
                await self.browser.page.fill(step_config["target"], step_config["input_data"]["value"], timeout=step_config.get("timeout", 30000))
                result = {"status": "success"}
            elif action_type == "wait":
                await self.browser.page.wait_for_timeout(step_config.get("input_data", {}).get("ms", 1000))
                result = {"status": "success"}
            elif action_type == "screenshot":
                path = f"artifacts/screenshots/{step_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                await self.browser.screenshot(path)
                result = {"status": "success", "screenshot_path": path}
            elif action_type == "assert_text":
                text = await self.browser.page.text_content(step_config["target"])
                expected = step_config["expected_outcome"]["text"]
                if expected in text:
                    result = {"status": "success"}
                else:
                    result = {"status": "failed", "error": f"Text not found: {expected}"}
            elif action_type == "assert_url":
                current_url = self.browser.page.url
                expected = step_config["expected_outcome"]["url_contains"]
                if expected in current_url:
                    result = {"status": "success"}
                else:
                    result = {"status": "failed", "error": f"URL mismatch: {current_url}"}
            else:
                result = {"status": "failed", "error": f"Unknown action type: {action_type}"}
            
            return result
        except Exception as e:
            logger.error("Step failed", step_id=step_id, error=str(e))
            return {"status": "failed", "error": str(e)}
