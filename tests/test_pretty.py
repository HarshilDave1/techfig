import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from techfig.engines.pretty import generate_pretty_image

@patch("techfig.engines.pretty.litellm.image_generation")
@patch("techfig.engines.pretty.convert_format")
def test_generate_pretty_image_url(mock_convert, mock_litellm, tmp_path):
    svg_path = tmp_path / "test.svg"
    svg_path.touch()
    out_png = tmp_path / "test_pretty.png"

    # Mock litellm returning a URL
    mock_response = MagicMock()
    mock_response.data = [MagicMock(url="http://fakeurl.com/img.png", b64_json=None)]
    mock_litellm.return_value = mock_response

    # Patch urllib to avoid actual download
    with patch("urllib.request.urlretrieve") as mock_urlretrieve:
        res = generate_pretty_image(svg_path, out_png, model="dall-e-3")
        
        mock_convert.assert_called_once()
        mock_litellm.assert_called_once()
        mock_urlretrieve.assert_called_once_with("http://fakeurl.com/img.png", str(out_png))
        assert res == str(out_png)

@patch("techfig.engines.pretty.litellm.image_generation")
@patch("techfig.engines.pretty.convert_format")
def test_generate_pretty_image_b64(mock_convert, mock_litellm, tmp_path):
    import base64
    svg_path = tmp_path / "test.svg"
    svg_path.touch()
    out_png = tmp_path / "test_pretty.png"

    # Mock litellm returning B64
    fake_b64 = base64.b64encode(b"fake image data").decode("utf-8")
    mock_response = MagicMock()
    mock_response.data = [MagicMock(url=None, b64_json=fake_b64)]
    mock_litellm.return_value = mock_response

    res = generate_pretty_image(svg_path, out_png, model="dall-e-3")
        
    mock_convert.assert_called_once()
    mock_litellm.assert_called_once()
    assert res == str(out_png)
    assert out_png.exists()
    assert out_png.read_bytes() == b"fake image data"
