"""Figure engine using matplotlib and seaborn to generate charts.

Takes normalized data and standard chart configurations to output
SVG/PNG files with scientific styling applied.
"""
import logging
from typing import Dict, Any, Union, Optional, List
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend BEFORE pyplot
import matplotlib.pyplot as plt  # noqa: E402
import seaborn as sns

from techfig.utils.data_loader import load_data, PlotData
from techfig.styles.presets import get_style

logger = logging.getLogger(__name__)

# All chart types the engine can produce
CHART_TYPES = ("bar", "line", "scatter", "box", "histogram", "heatmap")


def create_chart(
    data: Union[str, Path, PlotData],
    chart_type: str,
    output_path: str,
    title: str = "",
    x_col: Optional[str] = None,
    y_col: Optional[str] = None,
    hue_col: Optional[str] = None,
    xlabel: Optional[str] = None,
    ylabel: Optional[str] = None,
    style_name: str = "nature",
    style_overrides: Optional[Dict[str, Any]] = None,
) -> str:
    """Generate a data visualization chart.

    Args:
        data: File path or raw data structures.
        chart_type: One of ``bar``, ``line``, ``scatter``, ``histogram``,
            ``box``, ``heatmap``.
        output_path: Where to save the figure (.svg or .png).
        title: Figure title.
        x_col: Column name for X axis.
        y_col: Column name for Y axis.
        hue_col: Column name for grouping/coloring.
        xlabel: Custom X-axis label (defaults to ``x_col``).
        ylabel: Custom Y-axis label (defaults to ``y_col``).
        style_name: Name of the built-in style to apply.
        style_overrides: Additional rcParams to override the base style.

    Returns:
        The absolute path to the generated file.

    Raises:
        ValueError: If ``chart_type`` is not one of the supported types.
    """
    if chart_type not in CHART_TYPES:
        raise ValueError(
            f"Unsupported chart type: '{chart_type}'. "
            f"Supported types: {', '.join(CHART_TYPES)}"
        )

    # 1. Load data
    df = load_data(data)

    # 2. Apply styling
    base_style = get_style(style_name)

    # Separate diagram-only keys from matplotlib rcParams
    _ignored_keys = {"colors", "font_family", "font_size", "stroke_width"}
    rc_params = {
        k: v for k, v in base_style.items()
        if k not in _ignored_keys and not isinstance(v, dict)
    }
    if style_overrides:
        rc_params.update(style_overrides)

    with plt.rc_context(rc_params):
        sns.set_theme(style="whitegrid", rc=rc_params)

        figsize = rc_params.get("figure.figsize", (8, 6))
        fig, ax = plt.subplots(figsize=figsize)

        # Extract palette
        if "colors" in base_style:
            c = base_style["colors"]
            palette: List[str] = [
                c["primary"], c["secondary"], c["accent"],
                c["warning"], c["muted"],
            ]
            sns.set_palette(palette)

        # 3. Draw
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
        elif chart_type == "heatmap":
            # For heatmaps: if x_col and y_col given, pivot the data first
            if x_col and y_col:
                agg_col = hue_col or y_col
                pivot = df.pivot_table(index=y_col, columns=x_col, values=agg_col, aggfunc="mean")
                sns.heatmap(pivot, annot=True, fmt=".1f", ax=ax, cmap="YlOrRd")
            else:
                # Numeric columns only
                numeric_df = df.select_dtypes(include="number")
                sns.heatmap(numeric_df.corr(), annot=True, fmt=".2f", ax=ax, cmap="coolwarm")

        # 4. Polish
        if title:
            ax.set_title(title, pad=15)
        if xlabel:
            ax.set_xlabel(xlabel)
        if ylabel:
            ax.set_ylabel(ylabel)

        sns.despine(ax=ax)

        # 5. Save
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
