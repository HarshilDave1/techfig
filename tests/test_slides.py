"""Test the slide engine by generating a sample presentation."""
import os
import pytest
from techfig.engines.slides import create_presentation

def test_create_basic_presentation(tmp_path):
    """Test generating a simple PowerPoint presentation."""
    out_path = str(tmp_path / "test_presentation.pptx")
    
    slides = [
        {"title": "Welcome", "content": "This is the first slide\nHere is a bullet"},
        {"title": "Methodology", "content": "- Step 1\n- Step 2\n- Step 3"}
    ]
    
    returned_path = create_presentation(slides, out_path)
    
    assert returned_path == out_path
    assert os.path.exists(out_path)
    
    # Check that it's a non-empty PPTX file
    assert os.path.getsize(out_path) > 1000  # A basic pptx is usually ~30KB
