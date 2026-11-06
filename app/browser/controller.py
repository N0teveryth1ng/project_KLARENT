from playwright.async_api import async_playwright, Browser, Page
from typing import Optional
import os

from app.core.config import settings
from app.core.logging import logger


class BrowserController:
    def __init__(self):
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.allowed_domains = ["localhost", "127.0.0.1"]

    
    async def start(self, cookies: Optional[list[dict]] = None):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=settings.browser_headless,
        )
        context = await self.browser.new_context()

        if cookies:
            await context.add_cookies(cookies)

        self.page = await context.new_page()
        logger.info("Browser started")
        return self.page


    
    async def navigate(self, url: str):
        # Restrict navigation to allowed domains
        from urllib.parse import urlparse
        parsed = urlparse(url)
        if parsed.hostname not in self.allowed_domains:
            raise ValueError(f"Navigation to {parsed.hostname} not allowed. Only localhost allowed.")
        
        await self.page.goto(url, timeout=settings.browser_timeout)
        logger.info("Navigated", url=url)
    
    async def screenshot(self, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        await self.page.screenshot(path=path)
        logger.info("Screenshot taken", path=path)
        return path
    
    async def close(self):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        logger.info("Browser closed")
