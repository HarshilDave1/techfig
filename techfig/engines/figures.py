"""Figure engine using matplotlib and seaborn to generate charts.

Takes normalized data and standard chart configurations to output
SVG/PNG files with scientific styling applied.
"""
from typing import Dict, Any, Union, Optional
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import seaborn as sns

from techfig.utils.data_loader import load_data, PlotData
from techfig.styles.presets import get_style

# Use a non-interactive backend for server environments
matplotlib.use('Agg')

def create_chart(
    data: Union[str, Path, PlotData],
    chart_type: str,
    output_path: str,
    title: str = "",
    x_col: Optional[str] = None,
    y_col: Optional[str] = None,
    hue_col: Optional[str] = None,
    style_name: str = "nature",
    style_overrides: Optional[Dict[str, Any]] = None
) -> str:
    """Generate a data visualization chart.
    
    Args:
        data: File path or raw data structures.
        chart_type: Type of chart ('bar', 'line', 'scatter', 'histogram', 'box').
        output_path: Where to save the figure (.svg or .png).
        title: Figure title.
        x_col: Column name for X axis.
        y_col: Column name for Y axis.
        hue_col: Column name for grouping/coloring.
        style_name: Name of the built-in style to apply.
        style_overrides: Additional rcParams to override the base style.
        
    Returns:
        The absolute path to the generated file.
    """
    # 1. Load data
    df = load_data(data)
    
    # 2. Apply styling
    base_style = get_style(style_name)
    
    # Extract matplotlib rcParams (filtering out drawsvg-specific keys like "colors")
    ignored_keys = {"colors", "font_family", "font_size", "stroke_width"}
    rc_params = {k: v for k, v in base_style.items() if k not in ignored_keys and not isinstance(v, dict)}
    if style_overrides:
        rc_params.update(style_overrides)
        
    # Use seaborn's set_theme as a clean base, then update with our specific rcParams
    sns.set_theme(style="whitegrid")
    plt.rcParams.update(rc_params)
    
    # 3. Create figure and plot
    # figsize is applied by rcParams automatically, but explicit call is safer
    figsize = rc_params.get("figure.figsize", (8, 6))
    fig, ax = plt.subplots(figsize=figsize)
    
    # Extract palette
    palette = None
    if "colors" in base_style:
        c = base_style["colors"]
        # Create a categorical palette from our specific colors
        palette = [c["primary"], c["secondary"], c["accent"], c["warning"], c["muted"]]
        sns.set_palette(palette)
    
    # Draw logic based on chart_type
    if chart_type == "bar":
        sns.barplot(data=df, x=x_col, y=y_col, hue=hue_col, ax=ax)
    elif chart_type == "line":
        sns.lineplot(data=df, x=x_col, y=y_col, hue=hue_col, ax=ax)
    elif chart_type == "scatter":
        sns.scatterplot(data=df, x=x_col, y=y_col, hue=hue_col, ax=ax)
    elif chart_type == "box":
        sns.boxplot(data=df, x=x_col, y=y_col, hue=hue_col, ax=ax)
    elif chart_type == "histogram":
        sns.histplot(data=df, x=x_col, hue=hue_col, multiple="stack", ax=ax)
    else:
        raise ValueError(f"Unsupported chart type: {chart_type}")
        
    # 4. Polish and label
    if title:
        ax.set_title(title, pad=15)
        
    # Remove top and right spines for a clean scientific look
    sns.despine(ax=ax)
    
    # 5. Save output
    out_file = Path(output_path).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)
    
    fig.savefig(
        str(out_file), 
        format=out_file.suffix.replace('.', ''),
        dpi=rc_params.get("figure.dpi", 300),
        bbox_inches=rc_params.get("savefig.bbox", "tight")
    )
    
    plt.close(fig)  # Free memory
    
    return str(out_file)
