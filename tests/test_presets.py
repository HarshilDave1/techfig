"""Test the style presets module."""
import pytest
import warnings
from techfig.styles.presets import get_style, get_available_styles, load_custom_style


def test_get_available_styles():
    styles = get_available_styles()
    assert isinstance(styles, list)
    assert "nature" in styles
    assert "science" in styles
    assert "dark" in styles
    assert "presentation" in styles
    assert "minimal" in styles
    assert "metal" in styles
    assert "semiconductor" in styles
    assert "glass" in styles
    assert "dielectric" in styles
    assert "substrate" in styles
    # Should be sorted
    assert styles == sorted(styles)


def test_material_style_presets():
    metal = get_style("metal")
    semiconductor = get_style("semiconductor")
    glass = get_style("glass")
    dielectric = get_style("dielectric")
    substrate = get_style("substrate")

    assert metal["colors"]["background"] == "#F3F4F6"
    assert semiconductor["colors"]["primary"] == "#2563EB"
    assert glass["colors"]["stroke"] == "#7DD3FC"
    assert dielectric["colors"]["background"] == "#FAF5FF"
    assert substrate["colors"]["text"] == "#451A03"


def test_get_nature_style():
    s = get_style("nature")
    assert "colors" in s
    assert "primary" in s["colors"]
    assert "font_family" in s
    assert s["figure.dpi"] == 300


def test_get_dark_style():
    s = get_style("dark")
    assert s["colors"]["background"] == "#121212"
    assert s["axes.facecolor"] == "#121212"


def test_get_presentation_style():
    s = get_style("presentation")
    # Presentation should have larger fonts and lower DPI
    assert s["font_size"] == 24
    assert s["figure.dpi"] == 150


def test_get_minimal_style():
    s = get_style("minimal")
    assert s["axes.grid"] is False


def test_unknown_style_warns():
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        s = get_style("nonexistent")
        assert len(w) == 1
        assert "nonexistent" in str(w[0].message)
    # Should fall back to nature
    assert s == get_style("nature")


def test_case_insensitive():
    assert get_style("NATURE") == get_style("nature")
    assert get_style("Dark") == get_style("dark")


def test_load_custom_yaml(tmp_path):
    yaml_file = tmp_path / "custom.yaml"
    yaml_file.write_text("""
font_size: 20
stroke_width: 3.0
colors:
  primary: "#FF0000"
""")
    s = load_custom_style(str(yaml_file))
    assert s["font_size"] == 20
    assert s["stroke_width"] == 3.0
    assert s["colors"]["primary"] == "#FF0000"
    # Non-overridden keys should come from nature base
    assert s["colors"]["secondary"] == "#D55E00"


def test_load_custom_yaml_missing():
    with pytest.raises(FileNotFoundError):
        load_custom_style("/nonexistent/style.yaml")


def test_get_style_yaml_path(tmp_path):
    """get_style() should accept a YAML file path."""
    yaml_file = tmp_path / "mine.yaml"
    yaml_file.write_text("font_size: 99\n")
    s = get_style(str(yaml_file))
    assert s["font_size"] == 99
