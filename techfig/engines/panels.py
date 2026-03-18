import json
import logging
from typing import Dict, Any, Union
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from techfig.engines.figures import create_chart
from techfig.styles.presets import get_style

logger = logging.getLogger(__name__)

def create_figure_panel(spec: Union[str, Path, Dict[str, Any]], output_path: str) -> str:
    """Create a multi-panel figure from a specification.
    
    Args:
        spec: Path to JSON spec or a dict containing panel layout and charts.
        output_path: Where to save the multi-panel figure.
        
    Returns:
        Absolute path to the saved figure.
    """
    if isinstance(spec, (str, Path)):
        with open(spec, 'r') as f:
            data = json.load(f)
    else:
        data = spec
        
    # Get global config
    layout = data.get("layout", [1, 1])  # [rows, cols]
    rows, cols = layout[0], layout[1]
    
    style_name = data.get("style", "nature")
    base_style = get_style(style_name)
    
    _ignored_keys = {"colors", "font_family", "font_size", "stroke_width"}
    rc_params = {
        k: v for k, v in base_style.items()
        if k not in _ignored_keys and not isinstance(v, dict)
    }
    rc_params.update(data.get("style_overrides", {}))
    
    figsize = data.get("figsize", (8 * cols, 6 * rows))
    
    with plt.rc_context(rc_params):
        fig = plt.figure(figsize=figsize)
        
        if "title" in data:
            fig.suptitle(data["title"], fontsize=rc_params.get("axes.titlesize", 16), weight="bold")
            
        grid = plt.GridSpec(rows, cols, figure=fig)
        
        panels = data.get("panels", [])
        for i, panel in enumerate(panels):
            row = panel.get("row", 0)
            col = panel.get("col", 0)
            rowspan = panel.get("rowspan", 1)
            colspan = panel.get("colspan", 1)
            
            ax = fig.add_subplot(grid[row:row+rowspan, col:col+colspan])
            
            chart_config = panel.get("chart", {})
            chart_type = chart_config.get("type", "bar")
            chart_data = chart_config.get("data", [])
            
            # Pass ax and don't provide output_path so it doesn't save
            create_chart(
                data=chart_data,
                chart_type=chart_type,
                output_path="",
                title=chart_config.get("title", ""),
                x_col=chart_config.get("x_col"),
                y_col=chart_config.get("y_col"),
                hue_col=chart_config.get("hue_col"),
                xlabel=chart_config.get("xlabel"),
                ylabel=chart_config.get("ylabel"),
                style_name=style_name,
                style_overrides=chart_config.get("style_overrides"),
                ax=ax
            )
            
            # Add panel label (e.g. 'A', 'B') if requested
            # Classic Nature/Science style labels
            label = panel.get("label")
            if label:
                ax.text(-0.1, 1.05, label, transform=ax.transAxes, 
                        fontsize=rc_params.get("axes.titlesize", 14), fontweight='bold', va='top', ha='right')

        plt.tight_layout()
        if "title" in data:
            # Adjust top margin if suptitle is used
            fig.subplots_adjust(top=0.92)
            
        out_file = Path(output_path).resolve()
        out_file.parent.mkdir(parents=True, exist_ok=True)
        
        fmt = out_file.suffix.lstrip(".")
        if not fmt:
            fmt = "svg"
            out_file = out_file.with_suffix(".svg")
            
        fig.savefig(
            str(out_file),
            format=fmt,
            dpi=rc_params.get("figure.dpi", 300),
            bbox_inches=rc_params.get("savefig.bbox", "tight"),
        )
        plt.close(fig)
        
    return str(out_file)
