"""Example: Generate a bar chart from CSV data."""
from techfig.engines.figures import create_chart

# Generate a grouped bar chart with Nature journal styling
output = create_chart(
    data="examples/sample_data.csv",
    chart_type="bar",
    output_path="output/example_bar_chart.svg",
    title="Treatment vs Control Results",
    x_col="category",
    y_col="value",
    hue_col="group",
    xlabel="Experiment",
    ylabel="Measurement (units)",
    style_name="nature",
)
print(f"Chart saved to {output}")

# Try other styles:
# style_name="dark"        → dark background
# style_name="science"     → Science journal style
# style_name="presentation" → large fonts for slides
