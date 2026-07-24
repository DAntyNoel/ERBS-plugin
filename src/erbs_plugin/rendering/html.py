from __future__ import annotations

import asyncio
import os
import shutil
from dataclasses import asdict
from importlib.resources import files
from pathlib import Path
from typing import Any

from ..assets import AssetManager
from ..config import ERBSConfig
from ..exceptions import RenderFailed
from ..models import CardPayload


class HtmlCardRenderer:
    def __init__(self, config: ERBSConfig | None = None) -> None:
        self.config = config or ERBSConfig()
        self.assets = AssetManager(self.config.asset_directory)
        self._playwright: Any = None
        self._browser: Any = None
        self._lock = asyncio.Lock()
        self._render_count = 0

    async def __aenter__(self) -> HtmlCardRenderer:
        await self.start()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def start(self) -> None:
        if self._browser is not None:
            return
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise RenderFailed("请安装 erbs-plugin[render]") from exc
        browser_path = self.config.browser_path or self.discover_browser()
        if browser_path is None:
            raise RenderFailed("未找到 Chrome、Edge 或 Chromium")
        self._playwright = await async_playwright().start()
        try:
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                executable_path=str(browser_path),
                args=["--disable-gpu", "--no-sandbox", "--disable-setuid-sandbox"],
            )
        except Exception as exc:
            await self._playwright.stop()
            self._playwright = None
            raise RenderFailed(f"浏览器启动失败：{exc}") from exc

    async def close(self) -> None:
        if self._browser is not None:
            await self._browser.close()
        if self._playwright is not None:
            await self._playwright.stop()
        self._browser = None
        self._playwright = None

    async def render(self, payload: CardPayload) -> bytes:
        async with self._lock:
            await self.start()
            try:
                return await asyncio.wait_for(
                    self._render_page(payload), timeout=self.config.render_timeout_seconds
                )
            except TimeoutError as exc:
                await self._restart()
                raise RenderFailed("图片渲染超时") from exc
            except RenderFailed:
                raise
            except Exception as exc:
                await self._restart()
                raise RenderFailed(f"图片渲染失败：{exc}") from exc

    async def _render_page(self, payload: CardPayload) -> bytes:
        try:
            from jinja2 import Environment, StrictUndefined
        except ImportError as exc:
            raise RenderFailed("请安装 erbs-plugin[render]") from exc
        template_dir = files("erbs_plugin.rendering").joinpath("templates")
        template_text = template_dir.joinpath("card.html").read_text(encoding="utf-8")
        style_text = template_dir.joinpath("card.css").read_text(encoding="utf-8")
        env = Environment(autoescape=True, undefined=StrictUndefined)
        html = env.from_string(template_text).render(
            card=self._localize_images(asdict(payload)),
            style=style_text,
            scale=self.config.render_scale,
            asset_root=self.config.asset_directory.resolve().as_uri(),
        )
        page = await self._browser.new_page(device_scale_factor=1)
        try:
            await page.route(
                "**/*",
                lambda route: route.abort()
                if route.request.url.startswith(("http://", "https://"))
                else route.continue_(),
            )
            await page.set_content(html, wait_until="load")
            container = page.locator("#container")
            image = await container.screenshot(type="png")
        finally:
            await page.close()
        self._render_count += 1
        if self._render_count >= self.config.render_restart_after:
            await self._restart()
        return image

    def _localize_images(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {key: self._localize_images(child) for key, child in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._localize_images(child) for child in value]
        if isinstance(value, str) and value.startswith(("http://", "https://", "//")):
            return self.assets.resolve_source(value).resolve().as_uri()
        return value

    async def _restart(self) -> None:
        await self.close()
        self._render_count = 0

    @staticmethod
    def discover_browser() -> Path | None:
        configured = os.getenv("ERBS_RENDER_BROWSER")
        candidates = [
            configured,
            shutil.which("msedge"),
            shutil.which("microsoft-edge"),
            shutil.which("google-chrome"),
            shutil.which("chromium"),
            shutil.which("chromium-browser"),
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        ]
        for candidate in candidates:
            if candidate and Path(candidate).is_file():
                return Path(candidate)
        return None
