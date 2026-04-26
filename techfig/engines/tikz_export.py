"""LaTeX / TikZ export engine.

Converts chart specifications and node/edge diagrams into standalone
``.tex`` files using ``pgfplots`` (for charts) and ``tikz`` (for diagrams)
that can be ``\\input{}`` directly into a LaTeX paper.
"""
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd

from techfig.utils.data_loader import load_data, PlotData

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Charts → pgfplots
# ---------------------------------------------------------------------------

_PGFPLOTS_TEMPLATE = r"""\documentclass[border=5pt]{{standalone}}
\usepackage{{pgfplots}}
\pgfplotsset{{compat=newest}}
\usepackage{{xcolor}}

% Colorblind-safe palette (Wong 2011)
\definecolor{{cbblue}}{{HTML}}{{0072B2}}
\definecolor{{cborange}}{{HTML}}{{D55E00}}
\definecolor{{cbgreen}}{{HTML}}{{009E73}}
\definecolor{{cbyellow}}{{HTML}}{{F0E442}}
\definecolor{{cbsky}}{{HTML}}{{56B4E9}}

\begin{{document}}
\begin{{tikzpicture}}
\begin{{axis}}[
    title={{{title}}},
    xlabel={{{xlabel}}},
    ylabel={{{ylabel}}},
    {extra_opts}
]
{plot_commands}
\end{{axis}}
\end{{tikzpicture}}
\end{{document}}
"""


def chart_to_tikz(
    data: Union[str, Path, PlotData],
    chart_type: str,
    output_path: str,
    title: str = "",
    x_col: Optional[str] = None,
    y_col: Optional[str] = None,
    xlabel: Optional[str] = None,
    ylabel: Optional[str] = None,
) -> str:
    """Convert a chart specification into a pgfplots .tex file.

    Supports: bar, line, scatter.  Histogram/heatmap are not directly
    supported in pgfplots and will fall back to a table representation.

    Returns:
        Absolute path to the generated ``.tex`` file.
    """
    df = load_data(data)
    x_label = xlabel or x_col or "x"
    y_label = ylabel or y_col or "y"

    plot_commands = ""
    extra_opts = ""

    if chart_type == "bar":
        extra_opts = "ybar, bar width=12pt, enlarge x limits=0.15,\n    symbolic x coords={%s}" % (
            ",".join(str(v) for v in df[x_col].unique()) if x_col else ""
        )
        coords = _make_coords(df, x_col, y_col, symbolic_x=True)
        plot_commands = f"\\addplot[fill=cbblue] coordinates {{{coords}}};\n"

    elif chart_type == "line":
        coords = _make_coords(df, x_col, y_col)
        plot_commands = f"\\addplot[color=cbblue, thick, mark=*] coordinates {{{coords}}};\n"

    elif chart_type == "scatter":
        coords = _make_coords(df, x_col, y_col)
        plot_commands = (
            f"\\addplot[only marks, mark=*, color=cbblue] coordinates {{{coords}}};\n"
        )

    else:
        # Generic table fallback
        extra_opts = f"% NOTE: chart_type '{chart_type}' exported as table data"
        table_str = df.to_latex(index=False) if hasattr(df, "to_latex") else str(df)
        plot_commands = f"% Raw data:\n% {table_str}\n"

    tex = _PGFPLOTS_TEMPLATE.format(
        title=_escape_tex(title),
        xlabel=_escape_tex(x_label),
        ylabel=_escape_tex(y_label),
        extra_opts=extra_opts,
        plot_commands=plot_commands,
    )

    out = Path(output_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(tex, encoding="utf-8")
    return str(out)


# ---------------------------------------------------------------------------
# Diagrams → TikZ
# ---------------------------------------------------------------------------

_TIKZ_TEMPLATE = r"""\documentclass[border=10pt]{{standalone}}
\usepackage{{tikz}}
\usetikzlibrary{{arrows.meta, shapes.geometric, positioning}}
\usepackage{{xcolor}}

\definecolor{{cbblue}}{{HTML}}{{0072B2}}
\definecolor{{cborange}}{{HTML}}{{D55E00}}
\definecolor{{cbgreen}}{{HTML}}{{009E73}}
\definecolor{{cbyellow}}{{HTML}}{{F0E442}}
\definecolor{{cbsky}}{{HTML}}{{56B4E9}}

\begin{{document}}
\begin{{tikzpicture}}[
    >=Stealth,
    node distance=2cm,
    box/.style={{rectangle, draw=cbblue, fill=cbblue!15, rounded corners,
                 minimum width=2.5cm, minimum height=1cm, text centered, font=\small}},
    circ/.style={{circle, draw=cborange, fill=cborange!15,
                  minimum size=1.2cm, text centered, font=\small}},
    diam/.style={{diamond, draw=cbgreen, fill=cbgreen!15,
                  minimum width=2cm, minimum height=1.5cm, text centered, font=\small,
                  aspect=1.5}},
]
{node_commands}

{edge_commands}
\end{{tikzpicture}}
\end{{document}}
"""

_COLOR_MAP = {
    "primary": "cbblue",
    "secondary": "cborange",
    "accent": "cbgreen",
    "warning": "cbyellow",
    "muted": "cbsky",
}

_SHAPE_TO_STYLE = {
    "box": "box",
    "circle": "circ",
    "diamond": "diam",
}


def diagram_to_tikz(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    output_path: str,
) -> str:
    """Convert a node/edge diagram spec into a TikZ .tex file.

    Returns:
        Absolute path to the generated ``.tex`` file.
    """
    node_cmds: List[str] = []
    for node in nodes:
        nid = node.get("id", "node")
        text = _escape_tex(node.get("text", ""))
        shape = node.get("shape", "box")
        x = float(node.get("x", 0)) / 80  # scale from pixel coords to cm
        y = float(node.get("y", 0)) / -80  # invert Y for LaTeX coordinate system

        style = _SHAPE_TO_STYLE.get(shape, "box")
        node_cmds.append(f"\\node[{style}] ({nid}) at ({x:.1f},{y:.1f}) {{{text}}};")

    edge_cmds: List[str] = []
    for edge in edges:
        from_id = edge.get("from", "")
        to_id = edge.get("to", "")
        label = edge.get("label", "")

        if not from_id or not to_id:
            continue

        label_part = f' node[midway, above, font=\\footnotesize] {{{_escape_tex(label)}}}' if label else ""
        edge_cmds.append(f"\\draw[->] ({from_id}) --{label_part} ({to_id});")

    tex = _TIKZ_TEMPLATE.format(
        node_commands="\n".join(node_cmds),
        edge_commands="\n".join(edge_cmds),
    )

    out = Path(output_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(tex, encoding="utf-8")
    return str(out)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _escape_tex(text: str) -> str:
    """Escape special LaTeX characters."""
    replacements = {
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    for char, repl in replacements.items():
        text = text.replace(char, repl)
    return text


def _make_coords(
    df: pd.DataFrame,
    x_col: Optional[str],
    y_col: Optional[str],
    symbolic_x: bool = False,
) -> str:
    """Build a pgfplots ``coordinates`` string from a DataFrame."""
    if x_col and y_col:
        pairs = zip(df[x_col], df[y_col])
    elif x_col:
        pairs = enumerate(df[x_col])
    elif y_col:
        pairs = enumerate(df[y_col])
    else:
        pairs = enumerate(range(len(df)))

    parts: List[str] = []
    for x, y in pairs:
        if symbolic_x:
            parts.append(f"({x},{y})")
        else:
            parts.append(f"({x},{y})")
    return " ".join(parts)
