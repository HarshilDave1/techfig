"""Tests for techfig.utils.export — rasterizer backend ordering.

Verifies the P1-C reorder: Playwright (Chromium) is tried first for SVG→PNG,
falling back to rsvg-convert → cairosvg → inkscape only when Playwright is
unavailable or raises. PDF skips Playwright and starts at rsvg-convert.
"""
import sys
import types
import importlib

import pytest

from techfig.utils import export as export_mod


# ---------------------------------------------------------------------------
# Helpers: build a tiny valid SVG on disk
# ---------------------------------------------------------------------------

@pytest.fixture
def svg_file(tmp_path):
    p = tmp_path / "src.svg"
    p.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100">'
        '<rect width="200" height="100" fill="red"/></svg>'
    )
    return p


def _png_dst(tmp_path):
    return str(tmp_path / "out.png")


def _pdf_dst(tmp_path):
    return str(tmp_path / "out.pdf")


# ---------------------------------------------------------------------------
# PNG ordering
# ---------------------------------------------------------------------------

def test_png_prefers_playwright(svg_file, tmp_path, monkeypatch):
    """Playwright is attempted first; later backends are never touched."""
    calls = []

    def fake_pw(src, dst, dpi, width):
        calls.append(("playwright", src, dst))
        Path = type(svg_file)
        Path(dst).write_bytes(b"PNG-PLAYWRIGHT")

    monkeypatch.setattr(export_mod, "_svg_to_png_playwright", fake_pw)

    # Sabotage the later backends so any call to them would assert-fail.
    monkeypatch.setattr(export_mod, "_try_rsvg",
                        lambda *a, **k: pytest.fail("rsvg should not run"))
    monkeypatch.setattr(export_mod, "_try_cairosvg",
                        lambda *a, **k: pytest.fail("cairosvg should not run"))
    monkeypatch.setattr(export_mod, "_try_inkscape",
                        lambda *a, **k: pytest.fail("inkscape should not run"))

    dst = _png_dst(tmp_path)
    export_mod.convert_format(str(svg_file), dst)
    assert calls and calls[0][0] == "playwright"


def test_png_falls_back_to_rsvg_when_playwright_missing(svg_file, tmp_path, monkeypatch):
    """If Playwright raises ImportError, rsvg-convert is used next."""
    def pw_raises(src, dst, dpi, width):
        raise ImportError("no playwright")

    rsvg_calls = []

    def fake_rsvg(src, dst, fmt, dpi, width, errors):
        rsvg_calls.append((src, dst, fmt))
        # write a stub file so callers see a real output
        with open(dst, "wb") as fh:
            fh.write(b"PNG-RSVG")
        return True

    monkeypatch.setattr(export_mod, "_svg_to_png_playwright", pw_raises)
    monkeypatch.setattr(export_mod, "_try_rsvg", fake_rsvg)
    monkeypatch.setattr(export_mod, "_try_cairosvg",
                        lambda *a, **k: pytest.fail("cairosvg should not run"))
    monkeypatch.setattr(export_mod, "_try_inkscape",
                        lambda *a, **k: pytest.fail("inkscape should not run"))

    dst = _png_dst(tmp_path)
    export_mod.convert_format(str(svg_file), dst)
    assert rsvg_calls and rsvg_calls[0][2] == "png"


def test_png_falls_back_to_cairosvg(svg_file, tmp_path, monkeypatch):
    """Playwright and rsvg fail → cairosvg is tried."""
    monkeypatch.setattr(export_mod, "_svg_to_png_playwright",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("pw boom")))
    monkeypatch.setattr(export_mod, "_try_rsvg",
                        lambda *a, **k: False)

    cai_calls = []

    def fake_cairo(src, dst, fmt, dpi, width, errors):
        cai_calls.append((src, dst, fmt))
        with open(dst, "wb") as fh:
            fh.write(b"PNG-CAIRO")
        return True

    monkeypatch.setattr(export_mod, "_try_cairosvg", fake_cairo)
    monkeypatch.setattr(export_mod, "_try_inkscape",
                        lambda *a, **k: pytest.fail("inkscape should not run"))

    dst = _png_dst(tmp_path)
    export_mod.convert_format(str(svg_file), dst)
    assert cai_calls and cai_calls[0][2] == "png"


def test_png_all_backends_fail_raises(svg_file, tmp_path, monkeypatch):
    """All four backends unavailable → RuntimeError listing every attempt."""
    monkeypatch.setattr(export_mod, "_svg_to_png_playwright",
                        lambda *a, **k: (_ for _ in ()).throw(ImportError("no pw")))
    monkeypatch.setattr(export_mod, "_try_rsvg", lambda *a, **k: False)
    monkeypatch.setattr(export_mod, "_try_cairosvg", lambda *a, **k: False)
    monkeypatch.setattr(export_mod, "_try_inkscape", lambda *a, **k: False)

    with pytest.raises(RuntimeError) as excinfo:
        export_mod.convert_format(str(svg_file), _png_dst(tmp_path))

    msg = str(excinfo.value)
    # Each backend's error reason should be recorded.
    assert "playwright" in msg
    assert "rsvg" in msg
    assert "cairosvg" in msg
    assert "inkscape" in msg


# ---------------------------------------------------------------------------
# PDF ordering — Playwright must NOT be attempted for PDF
# ---------------------------------------------------------------------------

def test_pdf_skips_playwright(svg_file, tmp_path, monkeypatch):
    """SVG→PDF never calls Playwright; it starts with rsvg-convert."""
    monkeypatch.setattr(export_mod, "_svg_to_png_playwright",
                        lambda *a, **k: pytest.fail("playwright must not run for PDF"))

    rsvg_calls = []

    def fake_rsvg(src, dst, fmt, dpi, width, errors):
        rsvg_calls.append(fmt)
        with open(dst, "wb") as fh:
            fh.write(b"%PDF-1.4")
        return True

    monkeypatch.setattr(export_mod, "_try_rsvg", fake_rsvg)

    dst = _pdf_dst(tmp_path)
    export_mod.convert_format(str(svg_file), dst)
    assert rsvg_calls and rsvg_calls[0] == "pdf"


# ---------------------------------------------------------------------------
# Misc behavior
# ---------------------------------------------------------------------------

def test_same_format_copies(svg_file, tmp_path):
    dst = tmp_path / "copy.svg"
    export_mod.convert_format(str(svg_file), str(dst))
    assert dst.exists()
    assert dst.read_text() == svg_file.read_text()


def test_missing_source_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        export_mod.convert_format(str(tmp_path / "nope.svg"), _png_dst(tmp_path))


def test_unsupported_pair_raises(svg_file, tmp_path):
    dst = tmp_path / "out.jpg"
    with pytest.raises(ValueError):
        export_mod.convert_format(str(svg_file), str(dst))


# ---------------------------------------------------------------------------
# _svg_to_png_playwright actually invokes the Playwright API in order
# ---------------------------------------------------------------------------

def test_playwright_helper_uses_chromium_screenshot(svg_file, tmp_path, monkeypatch):
    """The Playwright helper locates the <svg> and screenshots it (mocked)."""
    captured = {}

    fake_page = types.SimpleNamespace(
        set_content=lambda html: captured.update(html=html),
        wait_for_timeout=lambda ms: None,
        locator=lambda sel: types.SimpleNamespace(
            first=types.SimpleNamespace(
                screenshot=lambda **kw: (
                    __import__("pathlib").Path(kw["path"]).write_bytes(b"PNG"),
                    captured.update(selector=sel),
                )[0]
            )
        ),
    )
    fake_browser = types.SimpleNamespace(
        new_page=lambda **kw: (captured.update(viewport=kw.get("viewport"),
                                              dsf=kw.get("device_scale_factor"))
                               or fake_page),
        close=lambda: captured.update(closed=True),
    )

    class FakePW:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        chromium = types.SimpleNamespace(
            launch=lambda headless: (captured.update(headless=headless) or fake_browser)
        )

    # Inject a fake `playwright.sync_api` module before the helper imports it.
    fake_mod = types.ModuleType("playwright.sync_api")
    setattr(fake_mod, "sync_playwright", FakePW)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake_mod)
    # Also ensure the parent package exists so the import line resolves.
    if "playwright" not in sys.modules:
        monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright"))

    dst = _png_dst(tmp_path)
    # Reload export so the helper picks up the patched module path cleanly.
    importlib.reload(export_mod)
    export_mod._svg_to_png_playwright(str(svg_file), dst, dpi=300)

    assert captured.get("headless") is True
    assert captured.get("selector") == "svg"
    assert captured.get("closed") is True
    # device_scale_factor should be dpi/96.
    assert captured.get("dsf") == pytest.approx(300 / 96.0)
    # The output file was written by the fake screenshot.
    with open(dst, "rb") as fh:
        assert fh.read() == b"PNG"
