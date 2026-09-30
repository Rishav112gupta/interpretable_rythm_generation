"""Image generation provider abstraction.

Providers return raw image bytes; storage and template composition are
handled elsewhere, so providers stay tiny and swappable.
"""

from __future__ import annotations

import base64
import hashlib
import io
import math
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx
from PIL import Image, ImageDraw, ImageFilter

from app.core.config import settings
from app.core.errors import ImageGenerationError


@dataclass
class ImageResult:
    data: bytes
    content_type: str
    provider: str
    model: str
    duration_ms: int


class ImageProvider(ABC):
    name = "base"
    model = ""

    @abstractmethod
    def generate(self, prompt: str, *, width: int = 1024, height: int = 1536) -> ImageResult: ...


class NoImageProvider(ImageProvider):
    """Used when IMAGE_PROVIDER=none: templates render without an AI image."""

    name = "none"

    def generate(self, prompt: str, *, width: int = 1024, height: int = 1536) -> ImageResult:
        raise ImageGenerationError("Image generation is disabled (IMAGE_PROVIDER=none). Upload an image instead.")


class MockImageProvider(ImageProvider):
    """Draws a deterministic abstract illustration locally (clearly not a real AI image)."""

    name = "mock"
    model = "mock-image-v1"

    def __init__(self, *, fail_times: int = 0) -> None:
        self.fail_times = fail_times

    def generate(self, prompt: str, *, width: int = 1024, height: int = 1536) -> ImageResult:
        if self.fail_times > 0:
            self.fail_times -= 1
            raise ImageGenerationError("Mock image generation failure (simulated).", transient=True)
        started = time.monotonic()
        h = hashlib.sha256(prompt.encode()).digest()
        c1 = (h[0], h[1], h[2])
        c2 = (h[3], h[4], h[5])
        img = Image.new("RGB", (width, height), c1)
        draw = ImageDraw.Draw(img)
        for y in range(height):
            t = y / height
            draw.line([(0, y), (width, y)], fill=tuple(int(c1[i] * (1 - t) + c2[i] * t) for i in range(3)))
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        odraw = ImageDraw.Draw(overlay)
        for i in range(7):
            r = 60 + h[6 + i] * 1.2
            cx = (h[13 + i] / 255) * width
            cy = (h[20 + i] / 255) * height
            odraw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255 - c1[0] // 2, 255 - c2[1] // 2, 200, 120))
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
        draw = ImageDraw.Draw(img)
        for k in range(12):
            angle = 2 * math.pi * k / 12
            x = width / 2 + math.cos(angle) * width * 0.3
            y = height / 2 + math.sin(angle) * width * 0.3
            draw.line([(width / 2, height / 2), (x, y)], fill=(255, 255, 255), width=3)
        img = img.filter(ImageFilter.GaussianBlur(1))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return ImageResult(buf.getvalue(), "image/png", self.name, self.model, int((time.monotonic() - started) * 1000))


class OpenAIImageProvider(ImageProvider):
    """OpenAI Images API (`/v1/images/generations`)."""

    name = "openai"

    def __init__(self, api_key: str, model: str, base_url: str, timeout: float) -> None:
        if not api_key:
            raise ImageGenerationError("IMAGE_API_KEY is not set for the OpenAI image provider.")
        self.model = model or "gpt-image-1"
        self.base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self.timeout = timeout

    def generate(self, prompt: str, *, width: int = 1024, height: int = 1536) -> ImageResult:
        started = time.monotonic()
        size = "1024x1536" if height > width else ("1536x1024" if width > height else "1024x1024")
        try:
            resp = httpx.post(
                f"{self.base_url}/images/generations",
                headers=self._headers,
                json={"model": self.model, "prompt": prompt, "size": size, "n": 1},
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise ImageGenerationError("Could not reach the image generation API.", transient=True) from exc
        if resp.status_code == 401:
            raise ImageGenerationError("Image API rejected the key (check IMAGE_API_KEY).")
        if resp.status_code == 429:
            raise ImageGenerationError("Image API rate limit reached. Try again shortly.", transient=True)
        if resp.status_code >= 400:
            msg = ""
            try:
                msg = resp.json().get("error", {}).get("message", "")
            except ValueError:
                pass
            raise ImageGenerationError(f"Image API error ({resp.status_code}). {msg}".strip(), transient=resp.status_code >= 500)
        try:
            item = resp.json()["data"][0]
        except (ValueError, KeyError, IndexError) as exc:
            raise ImageGenerationError("Unexpected response from the image API.") from exc
        if item.get("b64_json"):
            data = base64.b64decode(item["b64_json"])
        elif item.get("url"):
            try:
                data = httpx.get(item["url"], timeout=self.timeout).content
            except httpx.HTTPError as exc:
                raise ImageGenerationError("Could not download the generated image.", transient=True) from exc
        else:
            raise ImageGenerationError("Image API returned no image.")
        return ImageResult(data, "image/png", self.name, self.model, int((time.monotonic() - started) * 1000))


_override: ImageProvider | None = None


def get_image_provider() -> ImageProvider:
    if _override is not None:
        return _override
    p = settings.effective_image_provider
    if p == "openai":
        return OpenAIImageProvider(settings.image_api_key, settings.image_model, settings.image_base_url, settings.image_timeout_seconds)
    if p == "none":
        return NoImageProvider()
    return MockImageProvider()


def set_image_provider(provider: ImageProvider | None) -> None:
    global _override
    _override = provider
