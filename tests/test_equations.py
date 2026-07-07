"""Tests for the equation rendering engine (matplotlib mathtext)."""
import os

import pytest

from techfig.engines.equations import render_equation, _ensure_math_delimiters


# ---- delimiter wrapping ---------------------------------------------------

@pytest.mark.parametrize(
    "raw, expected",
    [
        (r"\nabla", r"$\nabla$"),
        (r"\nabla \cdot E", r"$\nabla \cdot E$"),
        # already-delimited strings are returned untouched
        (r"$\nabla$", r"$\nabla$"),
        (r"$$\nabla$$", r"$$\nabla$$"),
        (r"\(\nabla\)", r"\(\nabla\)"),
        (r"\[\nabla\]", r"\[\nabla\]"),
    ],
)
def test_ensure_math_delimiters(raw, expected):
    assert _ensure_math_delimiters(raw) == expected


def test_ensure_math_delimiters_empty_raises():
    with pytest.raises(ValueError, match="empty"):
        _ensure_math_delimiters("")
    with pytest.raises(ValueError, match="empty"):
        _ensure_math_delimiters("   ")


# ---- rendering ------------------------------------------------------------

def test_render_equation_svg(tmp_path):
    out = str(tmp_path / "eq.svg")
    result = render_equation(r"e^{i\pi} + 1 = 0", out)
    assert result == out
    assert os.path.exists(out)
    with open(out) as f:
        content = f.read()
    assert "<svg" in content
    assert "</svg>" in content


def test_render_equation_png(tmp_path):
    out = str(tmp_path / "eq.png")
    render_equation(r"\frac{a}{b}", out)
    assert os.path.exists(out)
    assert os.path.getsize(out) > 100


def test_render_equation_returns_absolute(tmp_path):
    out = str(tmp_path / "sub" / "eq.svg")
    result = render_equation(r"x^2", out)
    assert os.path.isabs(result)
    assert os.path.exists(result)


def test_render_equation_creates_parent_dir(tmp_path):
    out = str(tmp_path / "nested" / "deeper" / "eq.svg")
    render_equation(r"x^2", out)
    assert os.path.exists(out)


def test_render_equation_defaults_to_svg_when_no_extension(tmp_path):
    out = str(tmp_path / "eq_noext")
    result = render_equation(r"x^2", out)
    assert result.endswith(".svg")
    assert os.path.exists(result)


def test_render_equation_auto_wraps_undelimited(tmp_path):
    """A plain LaTeX snippet without $...$ should still render."""
    out = str(tmp_path / "eq.svg")
    render_equation(r"\nabla \cdot \mathbf{E} = \frac{\rho}{\varepsilon_0}", out)
    assert os.path.getsize(out) > 500  # mathtext SVGs are a few KB


def test_render_equation_accepts_inline_delimiters(tmp_path):
    out = str(tmp_path / "eq.svg")
    render_equation(r"\(\nabla \cdot E\)", out)
    assert os.path.exists(out)


def test_render_equation_accepts_display_delimiters(tmp_path):
    out = str(tmp_path / "eq.svg")
    render_equation(r"\[\int_0^\infty e^{-x^2} dx = \frac{\sqrt{\pi}}{2}\]", out)
    assert os.path.exists(out)


# ---- style presets --------------------------------------------------------

@pytest.mark.parametrize("style", ["nature", "science", "dark", "minimal", "presentation"])
def test_render_equation_styles(tmp_path, style):
    out = str(tmp_path / f"eq_{style}.svg")
    render_equation(r"a^2 + b^2 = c^2", out, style_name=style)
    assert os.path.exists(out)


def test_render_equation_dark_style_text_color(tmp_path):
    """Dark style should set a non-black text colour in the SVG."""
    out = str(tmp_path / "eq_dark.svg")
    render_equation(r"x = 1", out, style_name="dark")
    with open(out) as f:
        content = f.read()
    # dark style text colour is #E0E0E0 — mathtext embeds it as a fill/style
    assert "E0E0E0" in content.upper() or "#e0e0e0" in content


# ---- fontsize & dpi -------------------------------------------------------

def test_render_equation_fontsize_affects_size(tmp_path):
    import re

    small = str(tmp_path / "small.svg")
    large = str(tmp_path / "large.svg")
    render_equation(r"x^2", small, fontsize=12)
    render_equation(r"x^2", large, fontsize=48)

    def viewbox_area(path):
        with open(path) as f:
            m = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', f.read())
        assert m, f"no viewBox in {path}"
        return float(m.group(1)) * float(m.group(2))

    # Larger font ⇒ larger rendered extent ⇒ larger viewBox area.
    assert viewbox_area(large) > viewbox_area(small)


def test_render_equation_dpi_override(tmp_path):
    out = str(tmp_path / "eq.png")
    render_equation(r"x^2", out, dpi=72)
    assert os.path.exists(out)
    low = os.path.getsize(out)

    out2 = str(tmp_path / "eq_hi.png")
    render_equation(r"x^2", out2, dpi=300)
    high = os.path.getsize(out2)
    # higher DPI => more pixels => larger PNG
    assert high > low


def test_render_equation_style_overrides(tmp_path):
    out = str(tmp_path / "eq.svg")
    render_equation(r"x", out, style_overrides={"mathtext.fontset": "dejavusans"})
    assert os.path.exists(out)


# ---- error handling -------------------------------------------------------

def test_render_equation_empty_raises(tmp_path):
    with pytest.raises(ValueError, match="empty"):
        render_equation("", str(tmp_path / "eq.svg"))


def test_render_equation_invalid_mathtext_raises(tmp_path):
    with pytest.raises(ValueError, match="invalid mathtext"):
        render_equation(r"\notarealcommand{\foo}", str(tmp_path / "eq.svg"))
