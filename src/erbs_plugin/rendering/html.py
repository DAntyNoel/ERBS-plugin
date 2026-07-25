from __future__ import annotations

import asyncio
import base64
import mimetypes
import os
import shutil
from dataclasses import asdict
from datetime import UTC, datetime, timedelta, timezone
from functools import cache
from importlib.resources import files
from pathlib import Path
from typing import Any

from ..assets import AssetManager
from ..config import ERBSConfig
from ..exceptions import RenderFailed
from ..models import CardPayload


@cache
def _theme_asset(name: str, media_type: str) -> str:
    path = files("erbs_plugin.rendering").joinpath("theme", name)
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{media_type};base64,{encoded}"


def _theme() -> dict[str, str]:
    return {
        "logo": _theme_asset("eternal-return-logo.png", "image/png"),
        "bot_avatar": _theme_asset("erbs-bot.gif", "image/gif"),
        "player_emblem_background": _theme_asset(
            "player-emblem-background.png", "image/png"
        ),
        "font_semibold": _theme_asset("Rajdhani-SemiBold.ttf", "font/ttf"),
        "font_bold": _theme_asset("Rajdhani-Bold.ttf", "font/ttf"),
    }


def _footer_display_time(value: Any, config: ERBSConfig) -> tuple[str, str] | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    offset_hours = config.render_timezone_offset_hours
    fixed_timezone = timezone(
        timedelta(hours=offset_hours),
        name=config.render_timezone_name,
    )
    localized = parsed.astimezone(fixed_timezone)
    offset_sign = "+" if offset_hours >= 0 else "-"
    timezone_text = (
        f"{config.render_timezone_name} GMT{offset_sign}{abs(offset_hours)}"
    )
    return f"{localized.month}月{localized.day}日 {localized:%H:%M:%S}", timezone_text


class HtmlCardRenderer:
    def __init__(self, config: ERBSConfig | None = None) -> None:
        self.config = config or ERBSConfig()
        self.assets = AssetManager.discover(self.config.asset_directory)
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
        theme = _theme()
        card = self._localize_images(asdict(payload))
        footer = card.get("footer")
        if isinstance(footer, dict):
            display_time = _footer_display_time(footer.get("updatedAt"), self.config)
            if display_time is not None:
                footer["displayUpdatedAt"], footer["displayTimezone"] = display_time
        html = env.from_string(template_text).render(
            card=card,
            style=env.from_string(style_text).render(theme=theme),
            scale=self.config.render_scale,
            theme=theme,
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
            await page.evaluate("document.fonts.ready")
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
        if isinstance(value, str) and value.startswith("asset://"):
            path = self.assets.resolve_filename(value.removeprefix("asset://"))
        elif isinstance(value, str) and value.startswith(("http://", "https://", "//")):
            path = self.assets.resolve_source(value)
        else:
            return value
        if path.is_file():
            media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            return f"data:{media_type};base64,{encoded}"
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
