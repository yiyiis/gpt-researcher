"""MiniMax image generation provider for GPT Researcher.

This module provides image generation via MiniMax's API, supporting
the image-01 (imagegenerate) text-to-image model.

API docs (text-to-image): https://platform.minimax.io/docs/api-reference/image-generation-t2i
Endpoint path: /v1/image_generation
Auth: Bearer token via MINIMAX_API_KEY

Two regional hosts are supported (override via MINIMAX_API_HOST):
  - International: https://api.minimax.io        (default)
  - China:         https://api.minimaxi.com
"""

import asyncio
import hashlib
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# MiniMax host (overridable via MINIMAX_API_HOST for regional routing).
#   International users -> https://api.minimax.io
#   China users          -> https://api.minimaxi.com
DEFAULT_MINIMAX_HOST = "https://api.minimax.io"
# Official text-to-image path (note the underscore, not a slash).
IMAGE_GENERATION_PATH = "/v1/image_generation"

# Request timeout in seconds (MiniMax generation can take a while)
REQUEST_TIMEOUT_SECONDS = 120

# Map internal style hints to prompt prefixes (kept consistent with the
# dark-mode aesthetic of the GPT Researcher UI)
STYLE_PROMPT_PREFIX = {
    "dark": "Dark mode infographic style, teal accents, modern professional aesthetic.",
    "light": "Clean light infographic style, teal accents, modern professional aesthetic.",
    "auto": "Professional infographic style, modern aesthetic.",
}

# MiniMax supported aspect ratios (accepted by image-01)
SUPPORTED_ASPECT_RATIOS = {
    "1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "21:9",
}


class MinimaxImageGeneratorProvider:
    """Provider for generating images using MiniMax's image-01 API.

    Auth uses a Bearer token (MINIMAX_API_KEY). MINIMAX_GROUP_ID is read
    from the environment but only required by some endpoints; image
    generation currently relies on the API key alone.

    Attributes:
        model_name: The MiniMax model to use (default: "image-01").
        api_key: MiniMax API key from platform.minimaxi.com.
        group_id: Optional MiniMax group id.
        output_dir: Directory to save generated images.
    """

    DEFAULT_MODEL = "image-01"

    def __init__(
        self,
        model_name: Optional[str] = None,
        api_key: Optional[str] = None,
        group_id: Optional[str] = None,
        output_dir: str = "outputs",
    ):
        self.model_name = model_name or self.DEFAULT_MODEL
        self.api_key = api_key or os.getenv("MINIMAX_API_KEY")
        self.group_id = group_id or os.getenv("MINIMAX_GROUP_ID")
        # Regional host: international (api.minimax.io) or China (api.minimaxi.com)
        self.api_host = os.getenv("MINIMAX_API_HOST", DEFAULT_MINIMAX_HOST).rstrip("/")
        self.image_generation_url = f"{self.api_host}{IMAGE_GENERATION_PATH}"
        self.output_dir = Path(output_dir)

        if not self.api_key:
            logger.warning(
                "No MiniMax API key found. Set MINIMAX_API_KEY "
                "environment variable to enable image generation."
            )

    def _ensure_output_dir(self, research_id: str = "") -> Path:
        path = (
            self.output_dir / "images" / research_id
            if research_id
            else self.output_dir / "images"
        )
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _generate_filename(self, prompt: str, index: int = 0) -> str:
        prompt_hash = hashlib.md5(prompt.encode()).hexdigest()[:8]
        return f"img_{prompt_hash}_{index}.png"

    def _build_prompt(self, prompt: str, context: str, style: str) -> str:
        """Combine style prefix, prompt and optional context into one prompt."""
        prefix = STYLE_PROMPT_PREFIX.get(style, STYLE_PROMPT_PREFIX["auto"])
        parts = [prefix, prompt]
        if context:
            parts.append(context)
        return ". ".join(part.strip().rstrip(".") for part in parts if part) + "."

    def _normalize_aspect_ratio(self, aspect_ratio: str) -> str:
        """Clamp the requested aspect ratio to a value MiniMax accepts."""
        if aspect_ratio in SUPPORTED_ASPECT_RATIOS:
            return aspect_ratio
        logger.info(
            "Aspect ratio '%s' not supported by MiniMax, defaulting to 1:1",
            aspect_ratio,
        )
        return "1:1"

    async def generate_image(
        self,
        prompt: str,
        context: str = "",
        research_id: str = "",
        aspect_ratio: str = "1:1",
        num_images: int = 1,
        style: str = "dark",
    ) -> List[Dict[str, Any]]:
        """Generate images using MiniMax's text-to-image API.

        Args:
            prompt: The image generation prompt.
            context: Additional context (appended to prompt).
            research_id: Research ID for organizing output directories.
            aspect_ratio: Target aspect ratio (e.g. "16:9").
            num_images: Number of images to generate (1-9, per image-01).
            style: Style hint ("dark"/"light"/"auto").

        Returns:
            List of dicts with path, url, prompt, and alt_text keys.
        """
        if not self.api_key:
            logger.warning("No MiniMax API key set; skipping image generation.")
            return []

        output_path = self._ensure_output_dir(research_id)
        full_prompt = self._build_prompt(prompt, context, style)
        ratio = self._normalize_aspect_ratio(aspect_ratio)
        # MiniMax image-01 accepts n in [1, 9]; clamp the requested count.
        n = min(max(1, num_images), 9)

        # Single request carrying the official `n` field (one call, N images).
        image_urls = await self._request_images(full_prompt, ratio, n)

        if not image_urls:
            return []

        results: List[Dict[str, Any]] = []
        for i, url in enumerate(image_urls[:n]):
            item_bytes = await asyncio.to_thread(self._fetch_sync, url)
            if not item_bytes:
                continue
            filename = self._generate_filename(prompt, i)
            filepath = output_path / filename
            try:
                with open(filepath, "wb") as fh:
                    fh.write(item_bytes)
            except OSError as exc:
                logger.error(f"Failed to write MiniMax image {i}: {exc}")
                continue

            absolute_path = filepath.resolve()
            web_url = (
                f"/outputs/images/{research_id}/{filename}"
                if research_id
                else f"/outputs/images/{filename}"
            )
            results.append(
                {
                    "path": str(absolute_path),
                    "url": web_url,
                    "absolute_url": str(absolute_path),
                    "prompt": prompt,
                    "alt_text": f"Illustration: {prompt[:120]}",
                }
            )
            logger.info(f"MiniMax image saved to: {filepath}")

        return results

    async def _request_images(
        self,
        prompt: str,
        aspect_ratio: str,
        n: int,
    ) -> List[str]:
        """POST one image generation request and return image URLs.

        MiniMax returns `data.image_urls` (list of hosted URLs). We request
        with response_format="url" so the official download flow is used.
        Falls back to aiohttp, then requests in a thread.
        """
        payload: Dict[str, Any] = {
            "model": self.model_name,
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "n": n,
            "response_format": "url",
            # Let MiniMax refine the prompt for better quality.
            "prompt_optimizer": True,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}

        # Prefer aiohttp (non-blocking).
        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.image_generation_url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS),
                ) as resp:
                    body = await resp.json()
            return self._extract_image_urls(body)
        except ImportError:
            pass
        except Exception as exc:
            logger.error(f"MiniMax request failed (aiohttp): {exc}", exc_info=True)
            return []

        # Fallback: requests in a worker thread.
        import requests

        def _do_request() -> Dict[str, Any]:
            resp = requests.post(
                self.image_generation_url,
                json=payload,
                headers=headers,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            return resp.json()

        try:
            body = await asyncio.to_thread(_do_request)
            return self._extract_image_urls(body)
        except Exception as exc:
            logger.error(f"MiniMax request failed (requests): {exc}", exc_info=True)
            return []

    def _extract_image_urls(self, body: Dict[str, Any]) -> List[str]:
        """Parse the MiniMax response into a list of image URLs.

        Official shape (success):
            {"base_resp": {"status_code": 0, ...},
             "data": {"image_urls": ["https://...", ...], "created": ...}}

        Error shape:
            {"base_resp": {"status_code": <non-zero>, "status_msg": "..."}}
        """
        # Error envelope
        base_resp = body.get("base_resp") or {}
        status_code = base_resp.get("status_code", 0)
        if status_code != 0:
            msg = base_resp.get("status_msg", f"status_code={status_code}")
            logger.error(f"MiniMax API error: {msg}")
            return []

        # Success: data.image_urls
        data = body.get("data") or {}
        urls = data.get("image_urls") or data.get("images") or []
        if isinstance(urls, list):
            return [u for u in urls if isinstance(u, str) and u]

        # Defensive fallbacks for alternative shapes.
        if isinstance(data, dict):
            single = data.get("image_url") or data.get("url")
            if isinstance(single, str) and single:
                return [single]
        return []

    def _fetch_sync(self, url: str) -> Optional[bytes]:
        """Download image bytes from a URL (run synchronously, called from async)."""
        try:
            import requests

            resp = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
            resp.raise_for_status()
            return resp.content
        except Exception as exc:
            logger.error(f"Failed to download MiniMax image from {url}: {exc}")
            return None

    def is_available(self) -> bool:
        """Return True if the API key is configured."""
        return bool(self.api_key)

    @classmethod
    def from_config(cls, config) -> Optional["MinimaxImageGeneratorProvider"]:
        """Create a MinimaxImageGeneratorProvider from a Config object."""
        enabled = getattr(config, "IMAGE_GENERATION_ENABLED", False)
        provider = getattr(config, "IMAGE_GENERATION_PROVIDER", "google")
        if not enabled or provider != "minimax":
            return None
        model = getattr(config, "IMAGE_GENERATION_MODEL", None)
        return cls(model_name=model or cls.DEFAULT_MODEL)
