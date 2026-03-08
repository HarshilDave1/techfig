"""Batch generation engine.

Reads a YAML or JSON manifest file and generates all specified figures,
diagrams, and slides in one run.  This is useful for reproducible builds
of all visuals in a paper or project.
"""
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def batch_generate(
    spec_path: str,
    output_dir: Optional[str] = None,
) -> List[str]:
    """Generate all items described in a manifest file.

    Manifest format (YAML or JSON)::

        output_dir: ./output        # default output directory
        style: nature               # default style preset
        items:
          - type: chart
            data: results.csv
            chart_type: bar
            x_col: category
            y_col: value
            title: My Chart
            output: fig1.svg
          - type: diagram
            input: architecture.json
            output: fig2.svg
          - type: slides
            input: outline.json
            output: presentation.pptx
          - type: tikz_chart
            data: results.csv
            chart_type: line
            output: fig3.tex
          - type: tikz_diagram
            input: architecture.json
            output: fig4.tex

    Args:
        spec_path: Path to the manifest file (.yaml, .yml, or .json).
        output_dir: Override the manifest's ``output_dir``.

    Returns:
        List of absolute paths to all generated files.
    """
    spec = _load_spec(spec_path)

    base_dir = Path(spec_path).resolve().parent
    default_output_dir = Path(output_dir or spec.get("output_dir", "./output"))
    if not default_output_dir.is_absolute():
        default_output_dir = base_dir / default_output_dir
    default_output_dir.mkdir(parents=True, exist_ok=True)

    default_style = spec.get("style", "nature")
    items: List[Dict[str, Any]] = spec.get("items", [])
    results: List[str] = []

    for idx, item in enumerate(items):
        item_type = item.get("type", "")
        output_name = item.get("output", f"output_{idx}")
        output_path = str(default_output_dir / output_name)

        try:
            if item_type == "chart":
                out = _gen_chart(item, output_path, base_dir, default_style)
            elif item_type == "diagram":
                out = _gen_diagram(item, output_path, base_dir)
            elif item_type == "slides":
                out = _gen_slides(item, output_path, base_dir)
            elif item_type == "tikz_chart":
                out = _gen_tikz_chart(item, output_path, base_dir)
            elif item_type == "tikz_diagram":
                out = _gen_tikz_diagram(item, output_path, base_dir)
            else:
                logger.warning("Unknown item type '%s' at index %d — skipping", item_type, idx)
                continue

            results.append(out)
            logger.info("Generated: %s", out)
        except Exception as exc:
            logger.error("Failed to generate item %d (%s): %s", idx, item_type, exc)

    return results


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_spec(path: str) -> Dict[str, Any]:
    """Load a YAML or JSON manifest file."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Manifest not found: {path}")

    text = p.read_text(encoding="utf-8")

    if p.suffix in (".yaml", ".yml"):
        import yaml
        return yaml.safe_load(text) or {}
    elif p.suffix == ".json":
        return json.loads(text)
    else:
        # Try YAML first, fall back to JSON
        try:
            import yaml
            return yaml.safe_load(text) or {}
        except Exception:
            return json.loads(text)


def _resolve(base: Path, rel: str) -> str:
    """Resolve a potentially-relative path against a base directory."""
    p = Path(rel)
    if p.is_absolute():
        return str(p)
    return str(base / p)


def _gen_chart(item: Dict, output_path: str, base: Path, default_style: str) -> str:
    from techfig.engines.figures import create_chart

    data_path = _resolve(base, item["data"])
    return create_chart(
        data=data_path,
        chart_type=item.get("chart_type", "bar"),
        output_path=output_path,
        title=item.get("title", ""),
        x_col=item.get("x_col"),
        y_col=item.get("y_col"),
        hue_col=item.get("hue_col"),
        xlabel=item.get("xlabel"),
        ylabel=item.get("ylabel"),
        style_name=item.get("style", default_style),
    )


def _gen_diagram(item: Dict, output_path: str, base: Path) -> str:
    from techfig.engines.diagrams import create_flowchart

    input_path = _resolve(base, item["input"])
    with open(input_path) as f:
        data = json.load(f)
    return create_flowchart(
        nodes=data.get("nodes", []),
        edges=data.get("edges", []),
        output_path=output_path,
    )


def _gen_slides(item: Dict, output_path: str, base: Path) -> str:
    from techfig.engines.slides import create_presentation

    input_path = _resolve(base, item["input"])
    with open(input_path) as f:
        slides_data = json.load(f)
    return create_presentation(
        slides_data=slides_data,
        output_path=output_path,
        template_path=item.get("template"),
    )


def _gen_tikz_chart(item: Dict, output_path: str, base: Path) -> str:
    from techfig.engines.tikz_export import chart_to_tikz

    data_path = _resolve(base, item["data"])
    return chart_to_tikz(
        data=data_path,
        chart_type=item.get("chart_type", "bar"),
        output_path=output_path,
        title=item.get("title", ""),
        x_col=item.get("x_col"),
        y_col=item.get("y_col"),
        xlabel=item.get("xlabel"),
        ylabel=item.get("ylabel"),
    )


def _gen_tikz_diagram(item: Dict, output_path: str, base: Path) -> str:
    from techfig.engines.tikz_export import diagram_to_tikz

    input_path = _resolve(base, item["input"])
    with open(input_path) as f:
        data = json.load(f)
    return diagram_to_tikz(
        nodes=data.get("nodes", []),
        edges=data.get("edges", []),
        output_path=output_path,
    )
