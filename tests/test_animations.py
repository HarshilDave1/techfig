import pytest
import os
import json
from unittest.mock import patch, MagicMock
from techfig.engines.animations import create_animation, DiagramScene

# We use mocking extensively here because Manim relies on
# heavy system dependencies (Cairo, FFMPEG) and we want these
# unit tests to be fast and work across basic environments.

@pytest.fixture
def sample_spec():
    return {
        "elements": [
            {"id": "box1", "type": "box", "text": "Start", "x": 100, "y": 100},
            {"id": "circle1", "type": "circle", "text": "Process", "x": 300, "y": 100}
        ],
        "connections": [
            {"from": "box1", "to": "circle1", "label": "next"}
        ]
    }

def test_scene_initialization(sample_spec):
    # This should work without rendering if we don't call construct/render
    scene = DiagramScene(sample_spec)
    assert scene.spec == sample_spec

@patch("techfig.engines.animations.DiagramScene")
def test_create_animation_mocked(mock_scene_class, sample_spec, tmp_path):
    mock_scene_instance = MagicMock()
    mock_scene_class.return_value = mock_scene_instance
    
    spec_path = str(tmp_path / "test_spec.json")
    out_path = str(tmp_path / "out.mp4")
    
    with open(spec_path, "w") as f:
        json.dump(sample_spec, f)
        
    try:
        # Just calling it to see if it sets up the config and scene properly
        # We don't assert full file creation here because DiagramScene is mocked
        result = create_animation(spec_path, out_path, quality="l")
        
        # Verify it tries to use the engine
        mock_scene_class.assert_called_once_with(sample_spec)
        mock_scene_instance.render.assert_called_once()
    except ImportError:
        # If manim isn't installed locally, the import fails gracefully with our error handling
        pytest.skip("Manim not installed, skipping test.")
