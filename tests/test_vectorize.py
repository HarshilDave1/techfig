"""Test the vectorize engine."""
import os
import pytest
import numpy as np
from techfig.engines.vectorize import vectorize_image, vectorize_with_preset, VECTORIZE_PRESETS


@pytest.fixture
def sample_png(tmp_path):
    """Generate a simple test PNG image using matplotlib."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(3, 3))
    ax.plot([0, 1, 2], [0, 1, 0], "r-", linewidth=3)
    ax.set_title("Test")
    path = str(tmp_path / "test_input.png")
    fig.savefig(path, dpi=72)
    plt.close()
    return path


def test_vectorize_default(tmp_path, sample_png):
    out = str(tmp_path / "result.svg")
    result = vectorize_image(sample_png, out)
    assert result == out
    assert os.path.exists(out)
    with open(out) as f:
        content = f.read()
        assert "<svg" in content
        assert "path" in content.lower()


def test_vectorize_binary(tmp_path, sample_png):
    out = str(tmp_path / "binary.svg")
    result = vectorize_image(sample_png, out, color_mode="binary")
    assert os.path.exists(result)


def test_vectorize_low_precision(tmp_path, sample_png):
    out = str(tmp_path / "simple.svg")
    result = vectorize_image(sample_png, out, color_precision=2)
    assert os.path.exists(result)
    # Lower precision should produce a smaller file
    size_simple = os.path.getsize(result)

    out2 = str(tmp_path / "detailed.svg")
    vectorize_image(sample_png, out2, color_precision=8)
    size_detailed = os.path.getsize(out2)

    assert size_simple <= size_detailed


def test_preset_detailed(tmp_path, sample_png):
    out = str(tmp_path / "detailed.svg")
    result = vectorize_with_preset(sample_png, out, preset="detailed")
    assert os.path.exists(result)


def test_preset_sketch(tmp_path, sample_png):
    out = str(tmp_path / "sketch.svg")
    result = vectorize_with_preset(sample_png, out, preset="sketch")
    assert os.path.exists(result)


def test_preset_logo(tmp_path, sample_png):
    out = str(tmp_path / "logo.svg")
    result = vectorize_with_preset(sample_png, out, preset="logo")
    assert os.path.exists(result)


def test_preset_simplified(tmp_path, sample_png):
    out = str(tmp_path / "simplified.svg")
    result = vectorize_with_preset(sample_png, out, preset="simplified")
    assert os.path.exists(result)


def test_missing_input(tmp_path):
    with pytest.raises(FileNotFoundError):
        vectorize_image("/nonexistent/image.png", str(tmp_path / "out.svg"))


def test_unknown_preset(tmp_path, sample_png):
    with pytest.raises(ValueError, match="Unknown preset"):
        vectorize_with_preset(sample_png, str(tmp_path / "out.svg"), preset="foobar")


def test_auto_svg_extension(tmp_path, sample_png):
    """Output without .svg extension should get it appended."""
    out = str(tmp_path / "result")
    result = vectorize_image(sample_png, out)
    assert result.endswith(".svg")
    assert os.path.exists(result)
