"""Tests for raster image embed + optional image-gen panels.

Hybrid contract: vectors own labels/arrows/geometry. Image gen is only
for hard figures (3D models, photoreal insets) that sit *inside* the SVG.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from techfig.engines.diagrams import create_diagram
from techfig.engines.sketch_interpreter import get_diagram_schema, validate_spec
from techfig.utils.svg_builder import SVGBuilder


def _tiny_png(path: Path, color=(30, 90, 180), size=(24, 16)) -> Path:
    Image.new("RGB", size, color).save(path)
    return path


# ---- SVGBuilder.add_image --------------------------------------------------

class TestAddImage:
    def test_embeds_local_png_as_data_uri(self, tmp_path):
        src = _tiny_png(tmp_path / "inset.png")
        b = SVGBuilder(400, 300)
        b.add_image(0, 0, 80, 50, src=str(src), element_id="inset")
        out = str(tmp_path / "embed.svg")
        b.save(out)
        content = Path(out).read_text()
        assert "<image" in content
        assert "data:image/png;base64," in content
        raw = src.read_bytes()
        assert base64.b64encode(raw).decode("ascii") in content
        assert 'preserveAspectRatio="xMidYMid meet"' in content

    def test_missing_src_raises(self):
        b = SVGBuilder(400, 300)
        with pytest.raises(FileNotFoundError, match="image"):
            b.add_image(0, 0, 40, 40, src="/no/such/file.png")

    def test_registers_element_id(self, tmp_path):
        src = _tiny_png(tmp_path / "box.png")
        b = SVGBuilder(400, 300)
        b.add_image(12, -8, 60, 40, src=str(src), element_id="panel")
        assert "panel" in b._elements
        x, y, w, h = b._elements["panel"]
        assert x == pytest.approx(12)
        assert y == pytest.approx(-8)
        assert w == pytest.approx(60)
        assert h == pytest.approx(40)

    def test_optional_caption(self, tmp_path):
        src = _tiny_png(tmp_path / "cap.png")
        b = SVGBuilder(400, 300)
        b.add_image(0, 0, 80, 50, src=str(src), text="3D inset")
        out = str(tmp_path / "cap.svg")
        b.save(out)
        assert "3D inset" in Path(out).read_text()


# ---- image generation helper ----------------------------------------------

class TestGenerateFigureImage:
    def test_writes_png_via_injected_backend(self, tmp_path):
        from techfig.engines.image_gen import generate_figure_image

        payload = (tmp_path / "payload.png")
        _tiny_png(payload, color=(200, 40, 40))

        def fake_generate(prompt, **kwargs):
            assert "protein" in prompt.lower() or "3D" in prompt
            return payload.read_bytes()

        out = tmp_path / "cache" / "gen.png"
        result = generate_figure_image(
            "isometric 3D protein fold, no labels",
            output_path=str(out),
            generate_fn=fake_generate,
        )
        assert Path(result).exists()
        assert Path(result).read_bytes() == payload.read_bytes()

    def test_cache_hit_skips_backend(self, tmp_path):
        from techfig.engines.image_gen import generate_figure_image

        calls = {"n": 0}
        payload = _tiny_png(tmp_path / "once.png")

        def fake_generate(prompt, **kwargs):
            calls["n"] += 1
            return payload.read_bytes()

        cache_dir = tmp_path / "cache"
        first = generate_figure_image(
            "same prompt",
            cache_dir=str(cache_dir),
            generate_fn=fake_generate,
        )
        second = generate_figure_image(
            "same prompt",
            cache_dir=str(cache_dir),
            generate_fn=fake_generate,
        )
        assert first == second
        assert calls["n"] == 1

    def test_requires_prompt(self, tmp_path):
        from techfig.engines.image_gen import generate_figure_image

        with pytest.raises(ValueError, match="prompt"):
            generate_figure_image("", output_path=str(tmp_path / "x.png"))

    def test_prompt_wrapper_asks_for_no_text(self, tmp_path):
        from techfig.engines.image_gen import build_figure_prompt

        wrapped = build_figure_prompt("TEM of E. coli")
        assert "TEM of E. coli" in wrapped
        assert "no text" in wrapped.lower() or "no labels" in wrapped.lower()
        assert "scientific" in wrapped.lower()

    def test_venice_backend_when_key_present(self, tmp_path, monkeypatch):
        from techfig.engines import image_gen

        monkeypatch.setenv("VENICE_API_KEY", "test-key")
        fake_png = _tiny_png(tmp_path / "ven.png").read_bytes()

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return json.dumps({"images": [base64.b64encode(fake_png).decode("ascii")]}).encode()

        def fake_urlopen(req, timeout=60):
            assert "venice.ai" in getattr(req, "full_url", str(req))
            return _Resp()

        monkeypatch.setattr(image_gen.urllib.request, "urlopen", fake_urlopen)
        out = image_gen.generate_figure_image(
            "3D ribosome",
            output_path=str(tmp_path / "out.png"),
        )
        assert Path(out).read_bytes() == fake_png


# ---- diagram engine + schema ----------------------------------------------

class TestDiagramImageElement:
    def test_image_element_embeds_src(self, tmp_path):
        src = _tiny_png(tmp_path / "cell.png")
        elements = [
            {
                "type": "image",
                "id": "micrograph",
                "x": 0,
                "y": 0,
                "w": 120,
                "h": 80,
                "src": str(src),
            },
            {
                "type": "callout",
                "x": 140,
                "y": -40,
                "text": "nucleoid",
                "anchor": "micrograph",
            },
        ]
        out = create_diagram(elements, [], str(tmp_path / "hybrid.svg"))
        content = Path(out).read_text()
        assert "<image" in content
        assert "data:image/png;base64," in content
        assert "nucleoid" in content

    def test_image_element_generates_from_prompt(self, tmp_path):
        payload = _tiny_png(tmp_path / "payload.png", color=(10, 160, 80))

        def fake_generate(prompt, **kwargs):
            return payload.read_bytes()

        elements = [
            {
                "type": "image",
                "id": "fold",
                "x": -40,
                "y": 10,
                "w": 100,
                "h": 100,
                "prompt": "3D ribbon diagram of a TIM barrel, studio lighting",
                "cache_dir": str(tmp_path / "gencache"),
            }
        ]
        with patch(
            "techfig.engines.image_gen.default_generate",
            side_effect=fake_generate,
        ):
            out = create_diagram(elements, [], str(tmp_path / "gen.svg"))
        content = Path(out).read_text()
        assert "<image" in content
        assert base64.b64encode(payload.read_bytes()).decode("ascii") in content

    def test_image_missing_src_and_prompt_raises(self, tmp_path):
        with pytest.raises(ValueError, match="src|prompt"):
            create_diagram(
                [{"type": "image", "id": "x", "x": 0, "y": 0, "w": 40, "h": 40}],
                [],
                str(tmp_path / "err.svg"),
            )


class TestImageSpecSchema:
    def test_schema_includes_image(self):
        enum = get_diagram_schema()["properties"]["elements"]["items"]["properties"]["type"]["enum"]
        assert "image" in enum

    def test_validate_accepts_src_or_prompt(self):
        ok_src = validate_spec({
            "elements": [{"type": "image", "id": "a", "x": 0, "y": 0, "w": 40, "h": 40, "src": "a.png"}]
        })
        ok_prompt = validate_spec({
            "elements": [{"type": "image", "id": "b", "x": 0, "y": 0, "w": 40, "h": 40, "prompt": "3D ribosome"}]
        })
        assert ok_src == []
        assert ok_prompt == []

    def test_validate_image_needs_src_or_prompt(self):
        issues = validate_spec({"elements": [{"type": "image", "id": "x", "x": 0, "y": 0}]})
        assert any("src" in i or "prompt" in i for i in issues)
