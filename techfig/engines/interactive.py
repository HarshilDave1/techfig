import os
from typing import Optional, Union, Dict, List, Any

try:
    import plotly.express as px
    import plotly.graph_objects as go
except ImportError:
    px = None
    go = None

from techfig.utils.data_loader import load_data


def create_interactive_chart(
    data: Union[str, List[Dict[str, Any]], Dict[str, list]],
    chart_type: str,
    output_path: str,
    title: str = "",
    x_col: Optional[str] = None,
    y_col: Optional[str] = None,
    hue_col: Optional[str] = None,
    xlabel: Optional[str] = None,
    ylabel: Optional[str] = None,
    style_name: str = "nature",
) -> str:
    """
    Generate an interactive Plotly chart and save it as an HTML widget.
    
    Args:
        data: Path to data file or raw data structure
        chart_type: 'bar', 'line', 'scatter', 'histogram', 'box', 'heatmap'
        output_path: Path to save the .html file
        title: Chart title
        x_col: Column for X axis (if applicable)
        y_col: Column for Y axis (if applicable)
        hue_col: Column for grouping/coloring
        xlabel: Custom X axis label
        ylabel: Custom Y axis label
        style_name: Overall style theme name (basic mapping implemented)
        
    Returns:
        Absolute path to the saved generated HTML file
    """
    if px is None:
        raise ImportError("Plotly is required for interactive charts. Install it with `pip install plotly`.")

    df = load_data(data)
    
    # Clean up output path
    if not output_path.endswith(".html"):
        output_path += ".html"
        
    labels = {}
    if xlabel and x_col:
        labels[x_col] = xlabel
    if ylabel and y_col:
        labels[y_col] = ylabel

    # Map our style names to plotly templates roughly
    template = "plotly_white"
    if style_name == "dark":
        template = "plotly_dark"
    elif style_name == "minimal":
        template = "simple_white"

    fig = None
    
    if chart_type == "bar":
        fig = px.bar(df, x=x_col, y=y_col, color=hue_col, title=title, labels=labels, template=template)
    elif chart_type == "line":
        fig = px.line(df, x=x_col, y=y_col, color=hue_col, title=title, labels=labels, template=template)
    elif chart_type == "scatter":
        fig = px.scatter(df, x=x_col, y=y_col, color=hue_col, title=title, labels=labels, template=template)
    elif chart_type == "histogram":
        fig = px.histogram(df, x=x_col, color=hue_col, title=title, labels=labels, template=template)
    elif chart_type == "box":
        fig = px.box(df, x=x_col, y=y_col, color=hue_col, title=title, labels=labels, template=template)
    elif chart_type == "heatmap":
        # Heatmap assumes X, Y, and Z (hue_col is abused as Z values here, or we use index and columns if unshaped)
        # If standard df, we try to create an imshow
        # To match matplotlib behavior, if hue_col isn't specified, we might just pass the dataframe itself
        if x_col and y_col and hue_col:
             fig = px.density_heatmap(df, x=x_col, y=y_col, z=hue_col, title=title, labels=labels, template=template)
        else:
            # Fallback for structured 2D array data
            numeric_df = df.select_dtypes(include='number')
            fig = px.imshow(numeric_df, title=title, labels=labels, template=template)
    else:
        raise ValueError(f"Interactive chart type {chart_type} not supported yet.")

    # Enhance layout automatically for scientific context
    fig.update_layout(
        font=dict(family="Arial, sans-serif"),
        title_x=0.5,  # Center title
        title_font_size=20,
        margin=dict(l=60, r=40, t=60, b=60),
    )
    
    # Configure axes conditionally based on style specs if needed
    if style_name == "science" or style_name == "nature":
        fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='LightGray', zeroline=True, linewidth=1.5, linecolor='black', ticks="inside", mirror=True)
        fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='LightGray', zeroline=True, linewidth=1.5, linecolor='black', ticks="inside", mirror=True)

    abs_path = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    
    fig.write_html(
        abs_path,
        include_plotlyjs="cdn", # Keeps the HTML relatively small, fetches via CDN
        full_html=True
    )
    
    return abs_path
