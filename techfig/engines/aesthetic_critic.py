"""Aesthetic Critic for evaluating the visual quality of rendered SVG diagrams.

This module provides an **optional** scorer that leverages multimodal vision models
(via LiteLLM) to evaluate readability, professional appearance, and aesthetic
quality of a rendered diagram, providing actionable feedback for refinement.

IMPORTANT: This module requires an API key (e.g. ANTHROPIC_API_KEY) and is
entirely optional. The deterministic critique pipeline (see autoresearch.py)
does NOT import or depend on this module.

Agents can use render_to_png() as a standalone helper to convert SVG → PNG
for their own visual review, independently of score_aesthetic().
"""

import base64
import os
import tempfile
import json
from pathlib import Path
from typing import Tuple, Optional, Dict, Any

AESTHETIC_PROMPT = """\
You are an expert graphic designer and technical illustrator. Your job is to
evaluate the visual quality of the provided technical diagram.

Evaluate the diagram on the following criteria:
1. Color harmony: Are the colors professional, contrasting well, and not harsh?
2. Layout & Whitespace: Is the spacing balanced? Are elements crowded?
3. Typography: Is the text readable and appropriately sized?
4. Polish: Does it look like a high-quality, publication-ready figure rather than a messy draft?

Return your evaluation as a JSON object with EXACTLY two fields:
- "score": A float between 0.0 (terrible) and 1.0 (perfect publication quality).
- "feedback": A concise, actionable string explaining what looks bad and exactly how to fix it in the JSON spec (e.g., "Change the red box fill to a lighter pastel red and increase the font size.")

If the diagram is already an excellent minimum-viable schematic, give it a high score (0.8+).

Return ONLY valid JSON.
"""

def extract_json_from_response(text: str) -> Dict[str, Any]:
    """Safely extract JSON from a potentially markdown-fenced response."""
    # Try to find a JSON block
    if "```json" in text:
        parts = text.split("```json")
        if len(parts) > 1:
            body = parts[1].split("```")[0].strip()
            return json.loads(body)
    if "```" in text:
        parts = text.split("```")
        if len(parts) > 1:
            body = parts[1].split("```")[0].strip()
            return json.loads(body)
    
    # Try parsing directly
    return json.loads(text.strip())


def render_to_png(svg_path: str, png_path: str) -> None:
    """Render an SVG to a PNG using Playwright.

    This is a standalone helper that agents can use independently of
    score_aesthetic(). Useful for converting SVG → PNG for visual review.

    Args:
        svg_path: Path to the source SVG file.
        png_path: Path to write the output PNG file.

    Raises:
        RuntimeError: If Playwright is not installed or rendering fails.
    """
    from playwright.sync_api import sync_playwright
    
    svg_file = Path(svg_path).resolve()
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # 1200x800 is the default techfig canvas size
        page = browser.new_page(viewport={"width": 1200, "height": 800})
        
        # Inject SVG directly into a zero-margin HTML wrapper
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <body style="margin: 0; padding: 0; background: white; overflow: hidden; display: flex; justify-content: center; align-items: center; width: 100vw; height: 100vh;">
            {svg_file.read_text()}
        </body>
        </html>
        """
        page.set_content(html_content)
        
        # Wait a tick for SVG rendering
        page.wait_for_timeout(100)
        
        page.screenshot(path=png_path)
        browser.close()


def score_aesthetic(
    svg_path: str, 
    model: str = "anthropic/claude-3-5-sonnet-20241022",
    reference_image_path: Optional[str] = None
) -> Tuple[float, str]:
    """Score the aesthetic and visual quality of a rendered SVG diagram.
    
    ⚠ OPTIONAL — requires an API key (e.g. ANTHROPIC_API_KEY).
    The deterministic critique pipeline (autoresearch.critique_report) does
    NOT use this function. Agents call this only when they have vision model
    access and want a visual quality score.

    Args:
        svg_path: Path to the SVG file to evaluate.
        model: Multimodal LLM to use for vision scoring.
        reference_image_path: Optional path to the original rough sketch.
        
    Returns:
        (score, feedback_text)
        Score is 0.0 to 1.0
    """
    import shutil
    from litellm import completion
    
    svg_file = Path(svg_path)
    if not svg_file.exists():
        raise FileNotFoundError(f"SVG not found: {svg_path}")
        
    # 1. Convert SVG to PNG for the vision model
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir)
        temp_svg = temp_dir_path / "temp.svg"
        shutil.copy(svg_file, temp_svg)
        
        temp_png = temp_dir_path / "temp.png"
        
        try:
            render_to_png(str(temp_svg), str(temp_png))
        except Exception as e:
            return 0.0, f"Failed to render SVG to PNG for evaluation: {e}"
        
        # 2. Base64 encode the PNG
        with open(temp_png, "rb") as f:
            png_bytes = f.read()
        b64_img = base64.b64encode(png_bytes).decode("utf-8")
        data_uri = f"data:image/png;base64,{b64_img}"
        
        # 3. Formulate the API call
        content = [
            {"type": "text", "text": AESTHETIC_PROMPT},
            {
                "type": "image_url",
                "image_url": {
                    "url": data_uri
                }
            }
        ]
        
        if reference_image_path and os.path.exists(reference_image_path):
            with open(reference_image_path, "rb") as f:
                ref_bytes = f.read()
            # Crude guess of mime type
            ext = os.path.splitext(reference_image_path)[1].lower()
            mime = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"
            b64_ref = base64.b64encode(ref_bytes).decode("utf-8")
            ref_data_uri = f"data:{mime};base64,{b64_ref}"
            
            content.append({"type": "text", "text": "For context, here is the original sketch the diagram was generated from. Ensure the technical meaning is preserved."})
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": ref_data_uri
                }
            })
            
        messages = [
            {"role": "user", "content": content}
        ]

        # Ensure we have an API key or let litellm handle it via env fallback
        response = completion(
            model=model,
            messages=messages,
            temperature=0.1
        )
        
        res_text = response.choices[0].message.content
        
        try:
            data = extract_json_from_response(res_text)
            score = float(data.get("score", 0.5))
            feedback = str(data.get("feedback", "No feedback provided."))
            return max(0.0, min(1.0, score)), feedback
        except (json.JSONDecodeError, ValueError):
            # Fallback if model doesn't return proper JSON
            return 0.5, f"Warning: Failed to parse aesthetic feedback. Raw response: {res_text}"
