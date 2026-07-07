"""Tests for SVGBuilder style preset resolution.

Covers the fix from t_8e506a23 (merge: named-preset resolution):
- SVGBuilder must resolve {"name": "nature"} into the full nature preset dict.
- The "name" key must NOT be present in the resolved style.
- Semantic color keys (primary, secondary, ...) must resolve to hex strings,
  not remain as literal key names.
- Bare style_config dicts (no "name" key) must keep working (backward compat).
- Override dicts passed alongside {"name": ...} must merge on top of the preset.
"""
from techfig.utils.svg_builder import SVGBuilder


def test_named_preset_strips_name_key():
    b = SVGBuilder(style_config={"name": "nature"})
    assert "name" not in b.style


def test_named_preset_resolves_primary_to_hex():
    b = SVGBuilder(style_config={"name": "nature"})
    primary = b.style["colors"]["primary"]
    assert isinstance(primary, str)
    assert primary.startswith("#"), f"primary should be hex, got {primary!r}"


def test_named_preset_resolves_all_semantic_colors():
    b = SVGBuilder(style_config={"name": "nature"})
    for key in ("primary", "secondary", "accent", "background", "text"):
        value = b.style["colors"].get(key)
        assert value is not None, f"missing color {key}"
        assert value.startswith("#"), f"{key} should be hex, got {value!r}"


def test_named_preset_unknown_falls_back_to_nature():
    # get_style warns and returns NATURE_STYLE on unknown names
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        b = SVGBuilder(style_config={"name": "nonexistent_xyz"})
    assert b.style["colors"]["primary"].startswith("#")


def test_bare_dict_style_config_unchanged():
    """Backward compat: bare dicts without 'name' pass through as-is."""
    custom = {
        "font_size": 20,
        "colors": {"primary": "#FF0000"},
    }
    b = SVGBuilder(style_config=custom)
    assert "name" not in b.style
    assert b.style["font_size"] == 20
    assert b.style["colors"]["primary"] == "#FF0000"


def test_named_preset_with_overrides():
    """Caller-provided overrides must merge on top of the preset."""
    b = SVGBuilder(
        style_config={
            "name": "nature",
            "font_size": 42,
            "colors": {"primary": "#FF0000"},
        }
    )
    assert b.style["font_size"] == 42
    assert b.style["colors"]["primary"] == "#FF0000"
    # Other colors from the preset should remain
    assert b.style["colors"]["secondary"].startswith("#")


def test_stroke_color_helper_resolves_semantic_keys():
    """_stroke_color must resolve 'stroke' and any semantic color key."""
    b = SVGBuilder(style_config={"name": "nature"})
    stroke = b._stroke_color()
    assert stroke.startswith("#"), f"stroke should be hex, got {stroke!r}"
    # Resolving a semantic key should return the corresponding hex
    primary = b._stroke_color("primary")
    assert primary.startswith("#"), f"primary should be hex, got {primary!r}"


def test_arrow_xy_uses_resolved_stroke():
    """add_arrow_xy must not emit literal stroke names in the SVG."""
    b = SVGBuilder(style_config={"name": "nature"})
    b.add_arrow_xy(0, 0, 50, 50, stroke_color="primary")
    svg = b.get_svg_string()
    # The literal string 'stroke="primary"' must not appear
    assert 'stroke="primary"' not in svg


def test_add_line_uses_resolved_stroke():
    b = SVGBuilder(style_config={"name": "nature"})
    b.add_line(0, 0, 100, 0, stroke_color="primary")
    svg = b.get_svg_string()
    assert 'stroke="primary"' not in svg
