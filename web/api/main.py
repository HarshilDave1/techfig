"""TechFig Web API — FastAPI backend for the TechFig demo site.

Exposes the TechFig engines as REST endpoints for the Juno static frontend.
Pure-Python endpoints are unlimited; AI-powered endpoints are rate-limited.

Environment variables (set on Railway):
    VENICE_API_KEY   — Venice AI API key for LLM calls
    VENICE_API_BASE  — Venice API base URL (https://api.venice.ai/api/v1)
    ALLOWED_ORIGINS  — Comma-separated CORS origins (e.g., your Juno satellite URL)
"""

import io
import json
import os
import tempfile
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# ── TechFig engine imports ────────────────────────────────────────────────
from techfig.engines.diagrams import create_diagram
from techfig.engines.sketch_interpreter import (
    SKETCH_PROMPT,
    render_from_spec,
    validate_spec,
)
from techfig.engines.figures import create_chart, CHART_TYPES
from techfig.styles.presets import get_available_styles

# ── App setup ─────────────────────────────────────────────────────────────

app = FastAPI(
    title="TechFig API",
    description="REST API for the TechFig scientific visualization toolkit",
    version="0.1.0",
)

# CORS — allow the Juno frontend to call us
allowed_origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Rate limiter (simple in-memory, per-IP) ───────────────────────────────

RATE_LIMIT_MAX = 5  # requests per window
RATE_LIMIT_WINDOW = 60  # seconds
_rate_store: Dict[str, List[float]] = defaultdict(list)


def _check_rate_limit(ip: str) -> bool:
    """Return True if the request is allowed, False if rate-limited."""
    now = time.time()
    timestamps = _rate_store[ip]
    # Remove expired timestamps
    _rate_store[ip] = [t for t in timestamps if now - t < RATE_LIMIT_WINDOW]
    if len(_rate_store[ip]) >= RATE_LIMIT_MAX:
        return False
    _rate_store[ip].append(now)
    return True


# ── Request models ────────────────────────────────────────────────────────


class DiagramRequest(BaseModel):
    elements: List[Dict[str, Any]]
    connections: List[Dict[str, Any]] = []
    width: int = 1200
    height: int = 800
    style: Optional[str] = None


class ChartRequest(BaseModel):
    data: Any  # JSON tabular data
    chart_type: str
    title: str = ""
    x_col: Optional[str] = None
    y_col: Optional[str] = None
    hue_col: Optional[str] = None
    xlabel: Optional[str] = None
    ylabel: Optional[str] = None
    style: str = "nature"


class ReconstructRequest(BaseModel):
    spec: Dict[str, Any]
    style: Optional[str] = None


class ChatRequest(BaseModel):
    message: str
    current_spec: Optional[Dict[str, Any]] = None  # For refinement


# ── Template loading ──────────────────────────────────────────────────────

TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "techfig" / "templates"


def _load_templates() -> Dict[str, Any]:
    """Load all JSON templates from the templates directory."""
    templates = {}
    if TEMPLATES_DIR.exists():
        for f in TEMPLATES_DIR.glob("*.json"):
            try:
                with open(f) as fh:
                    templates[f.stem] = json.load(fh)
            except Exception:
                pass
    return templates


# ── Helper: render spec to SVG string ─────────────────────────────────────


def _render_spec_to_svg(spec: Dict[str, Any], style_name: Optional[str] = None) -> str:
    """Render a diagram spec to SVG and return the SVG as a string."""
    # Load style config if specified
    style_config = None
    if style_name:
        from techfig.styles.presets import load_style
        try:
            style_config = load_style(style_name)
        except Exception:
            pass

    with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        render_from_spec(spec, tmp_path, style_config=style_config)
        with open(tmp_path, "r") as f:
            return f.read()
    finally:
        os.unlink(tmp_path)


# ══════════════════════════════════════════════════════════════════════════
# FREE TIER ENDPOINTS (no LLM, unlimited)
# ══════════════════════════════════════════════════════════════════════════


@app.get("/api/health")
async def health():
    """Health check."""
    return {"status": "ok", "version": "0.1.0"}


@app.get("/api/styles")
async def list_styles():
    """List available style presets."""
    return {"styles": get_available_styles()}


@app.get("/api/templates")
async def list_templates():
    """List built-in demo templates with their specs."""
    templates = _load_templates()
    return {"templates": {name: spec for name, spec in templates.items()}}


@app.post("/api/diagram")
async def generate_diagram(req: DiagramRequest):
    """Generate an SVG diagram from elements + connections spec."""
    spec = {
        "elements": req.elements,
        "connections": req.connections,
        "canvas": {"width": req.width, "height": req.height},
    }

    issues = validate_spec(spec)
    if issues:
        raise HTTPException(status_code=422, detail={"validation_errors": issues})

    try:
        svg = _render_spec_to_svg(spec, req.style)
        return {"svg": svg, "spec": spec}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/reconstruct")
async def reconstruct_diagram(req: ReconstructRequest):
    """Render an SVG from a full diagram spec (e.g., from template picker)."""
    issues = validate_spec(req.spec)
    if issues:
        raise HTTPException(status_code=422, detail={"validation_errors": issues})

    try:
        svg = _render_spec_to_svg(req.spec, req.style)
        return {"svg": svg, "spec": req.spec}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chart")
async def generate_chart(req: ChartRequest):
    """Generate a chart as SVG."""
    if req.chart_type not in CHART_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown chart type: {req.chart_type}. Available: {list(CHART_TYPES)}",
        )

    with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        create_chart(
            data=req.data,
            chart_type=req.chart_type,
            output_path=tmp_path,
            title=req.title,
            x_col=req.x_col,
            y_col=req.y_col,
            hue_col=req.hue_col,
            xlabel=req.xlabel,
            ylabel=req.ylabel,
            style_name=req.style,
        )
        with open(tmp_path, "r") as f:
            svg = f.read()
        return {"svg": svg}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        os.unlink(tmp_path)


# ══════════════════════════════════════════════════════════════════════════
# AI-POWERED ENDPOINTS (LLM via Venice, rate-limited: 5 req/min per IP)
# ══════════════════════════════════════════════════════════════════════════


@app.post("/api/chat")
async def chat_to_diagram(req: ChatRequest, request: Request):
    """Convert natural language to a diagram via LLM.

    If `current_spec` is provided, the LLM refines the existing diagram
    based on the user's message (e.g., "make the boxes blue").
    """
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Max 5 AI requests per minute.")

    # TODO: Implement LLM call via litellm + Venice API
    # Placeholder: return a helpful message about what will happen
    return {
        "status": "placeholder",
        "message": (
            "LLM chat endpoint not yet implemented. "
            "When complete, this will send your message to Venice AI "
            "with TechFig's SKETCH_PROMPT, receive a JSON diagram spec, "
            "validate it, render SVG, and return both."
        ),
        "user_message": req.message,
        "has_existing_spec": req.current_spec is not None,
    }


@app.post("/api/sketch")
async def sketch_to_diagram(request: Request, image: UploadFile = File(...)):
    """Upload a sketch image and reconstruct it as an SVG diagram via LLM vision."""
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Max 5 AI requests per minute.")

    # Validate file type
    if image.content_type not in ("image/jpeg", "image/png", "image/webp", "image/gif"):
        raise HTTPException(status_code=422, detail=f"Unsupported image type: {image.content_type}")

    # TODO: Implement LLM vision call via litellm + Venice API
    # Placeholder: return info about what will happen
    image_bytes = await image.read()
    return {
        "status": "placeholder",
        "message": (
            "Sketch-to-diagram endpoint not yet implemented. "
            "When complete, this will encode your image as base64, "
            "send it to Venice's vision model with TechFig's SKETCH_PROMPT, "
            "receive a JSON diagram spec, render SVG, and return both."
        ),
        "image_size_bytes": len(image_bytes),
        "image_type": image.content_type,
    }
