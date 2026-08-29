"""Generate raster insets for hard figures and embed them in vector diagrams.

Use this when a reconstruct spec needs a 3D model, micrograph-like inset,
or other photoreal panel that boxes/pen/compound cannot express. Labels,
arrows, and geometry stay as SVG vectors — the raster is only the inset.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import urllib.request
from pathlib import Path
from typing import Callable, Optional

GenerateFn = Callable[..., bytes]

VENICE_GENERATE_URL = "https://api.venice.ai/api/v1/image/generate"
DEFAULT_VENICE_MODEL = "gpt-image-2"
DEFAULT_LITELLM_MODEL = "openai/dall-e-3"

_NO_TEXT_WRAPPER = (
    "Scientific illustration. {user}. "
    "No text, no labels, no watermarks, no captions, no letters. "
    "Clean studio lighting, publication-quality, isolated subject."
)


def build_figure_prompt(user_prompt: str) -> str:
    """Wrap a user prompt so the model does not paint labels into the raster."""
    user = (user_prompt or "").strip()
    if not user:
        raise ValueError("prompt is required")
    return _NO_TEXT_WRAPPER.format(user=user)


def _cache_key(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]


def _venice_generate(prompt: str, **kwargs) -> bytes:
    """POST /image/generate and return decoded image bytes."""
    key = os.environ.get("VENICE_API_KEY")
    if not key:
        raise RuntimeError("VENICE_API_KEY is not set")
    model = kwargs.get("model") or DEFAULT_VENICE_MODEL
    body = {
        "model": model,
        "prompt": prompt,
        "width": int(kwargs.get("width", 1024)),
        "height": int(kwargs.get("height", 1024)),
        "format": "png",
        "safe_mode": False,
        "hide_watermark": True,
        "return_binary": False,
    }
    if kwargs.get("style_preset"):
        body["style_preset"] = kwargs["style_preset"]
    req = urllib.request.Request(
        VENICE_GENERATE_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=int(kwargs.get("timeout", 180))) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    images = payload.get("images") or []
    if not images:
        raise RuntimeError("Venice image generation returned no images")
    return base64.b64decode(images[0])


def _litellm_generate(prompt: str, **kwargs) -> bytes:
    import litellm

    model = kwargs.get("model") or DEFAULT_LITELLM_MODEL
    response = litellm.image_generation(prompt=prompt, model=model, n=1)
    data = getattr(response, "data", None) or []
    if not data:
        raise RuntimeError("image generation returned no data")
    data0 = data[0]
    b64 = getattr(data0, "b64_json", None)
    if b64:
        return base64.b64decode(b64)
    url = getattr(data0, "url", None)
    if url:
        with urllib.request.urlopen(url) as fh:  # noqa: S310 — caller-controlled URL
            return fh.read()
    raise RuntimeError("image generation returned no url or b64 data")


def default_generate(prompt: str, **kwargs) -> bytes:
    """Generate image bytes.

    Prefers Venice ``POST /image/generate`` when ``VENICE_API_KEY`` is set
    (good for gpt-image-2 / 3D-style insets). Falls back to litellm
    (``openai/dall-e-3``) otherwise. Tests inject ``generate_fn``.
    """
    model = kwargs.get("model")
    force_litellm = bool(model) and str(model).startswith(("openai/", "azure/", "gemini/"))
    if os.environ.get("VENICE_API_KEY") and not force_litellm:
        return _venice_generate(prompt, **kwargs)
    return _litellm_generate(prompt, **kwargs)


def generate_figure_image(
    prompt: str,
    output_path: Optional[str] = None,
    cache_dir: Optional[str] = None,
    generate_fn: Optional[GenerateFn] = None,
    **kwargs,
) -> str:
    """Generate (or cache-hit) a PNG and return its path.

    ``generate_fn(prompt, **kwargs) -> bytes`` is injectable so tests never
    hit a network. Production uses :func:`default_generate`.
    """
    user = (prompt or "").strip()
    if not user:
        raise ValueError("prompt is required")
    wrapped = build_figure_prompt(user)
    key = _cache_key(wrapped)

    cache_path: Optional[Path] = None
    if cache_dir:
        cache_path = Path(cache_dir) / f"{key}.png"
        if cache_path.exists():
            if output_path:
                dest = Path(output_path)
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(cache_path.read_bytes())
                return str(dest)
            return str(cache_path)

    fn = generate_fn or default_generate
    blob = fn(wrapped, **kwargs)
    if not blob:
        raise RuntimeError("image generation returned empty bytes")

    if output_path:
        dest = Path(output_path)
    elif cache_path is not None:
        dest = cache_path
    else:
        dest = Path.cwd() / f"techfig_gen_{key}.png"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(blob)
    return str(dest)
