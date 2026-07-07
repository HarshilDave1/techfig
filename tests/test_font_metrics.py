"""Tests for real font-metric text-width measurement in svg_builder.

Replaces the old ``len(text) * size * 0.6`` heuristic, which over-estimated
narrow glyphs (``iii``) and under-estimated wide ones (``WWW``).
"""
from techfig.utils.svg_builder import SVGBuilder, _text_width


def _heuristic(text: str, size: float) -> float:
    return len(text) * size * 0.6


class TestFontMetrics:
    def test_narrow_glyphs_shorter_than_heuristic(self):
        real = _text_width("iiiiii", "Arial, Helvetica, sans-serif", 14)
        assert real < _heuristic("iiiiii", 14) * 0.7

    def test_wide_glyphs_match_or_exceed_heuristic(self):
        real = _text_width("WWWWWW", "Arial, Helvetica, sans-serif", 14)
        assert real >= _heuristic("WWWWWW", 14) * 0.9

    def test_add_text_stores_real_width(self):
        b = SVGBuilder(400, 300)
        b.add_text(0, 0, text="Hello World", element_id="t")
        _, _, w, _ = b._elements["t"]
        # real measurement ~80px; the old heuristic would give 92px
        assert 60 < w < 90

    def test_fallback_to_heuristic_on_missing_font(self):
        real = _text_width("Hello", "definitely-not-a-real-font-family", 14)
        assert abs(real - _heuristic("Hello", 14)) < 0.01

    def test_size_scales_width(self):
        small = _text_width("Data", "Arial, Helvetica, sans-serif", 10)
        large = _text_width("Data", "Arial, Helvetica, sans-serif", 40)
        assert large > small * 3  # ~4x wider, allow font-metric slack
