import subprocess
import sys
import json

def run_cli(args):
    return subprocess.run(
        [sys.executable, "-m", "techfig.cli"] + args,
        capture_output=True,
        text=True,
    )

def test_cli_help():
    res = run_cli(["--help"])
    assert res.returncode == 0
    assert "TechFig: Technical Graphic Generator for Scientists" in res.stdout

def test_cli_subcommands_help():
    subcommands = [
        "chart", "diagram", "slides", "tikz", "export", "batch",
        "sketch", "reconstruct", "critique", "animate", "panel",
        "equation", "animate-svg", "math-widget", "diagram-anim",
        "prompt", "styles", "config", "components"
    ]
    for sub in subcommands:
        res = run_cli([sub, "--help"])
        assert res.returncode == 0
        assert sub in res.stdout or "help" in res.stdout

def test_cli_styles():
    res = run_cli(["styles"])
    assert res.returncode == 0
    assert "Available style presets:" in res.stdout
    assert "nature" in res.stdout

def test_cli_config_list():
    res = run_cli(["config", "list"])
    assert res.returncode == 0

def test_cli_critique_and_fix(tmp_path):
    # Create a simple invalid/off-grid diagram spec
    spec = {
        "elements": [
            {"type": "box", "id": "b1", "x": 10.3, "y": 20.7, "w": 100, "h": 60},
            {"type": "box", "id": "b2", "x": 10.4, "y": 90.1, "w": 100, "h": 60}
        ]
    }
    spec_path = tmp_path / "spec.json"
    svg_path = tmp_path / "out.svg"
    with open(spec_path, "w") as f:
        json.dump(spec, f)

    # run critique without fix
    res = run_cli(["critique", "--input", str(spec_path), "--svg-output", str(svg_path)])
    assert res.returncode == 0
    assert "Score:" in res.stdout
    assert "is not aligned" in res.stdout

    # run critique with fix
    res_fix = run_cli(["critique", "--input", str(spec_path), "--svg-output", str(svg_path), "--fix"])
    assert res_fix.returncode == 0
    assert "Applied auto-fixes" in res_fix.stdout

    # Check that it updated the spec file
    with open(spec_path, "r") as f:
        updated_spec = json.load(f)
    # The x coordinates should now be snapped (e.g. to 10.0) and aligned (exactly equal)
    assert updated_spec["elements"][0]["x"] == 10.0
    assert updated_spec["elements"][1]["x"] == 10.0
