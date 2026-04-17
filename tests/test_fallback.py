import pytest
from unittest.mock import patch, MagicMock
try:
    import schemdraw.elements as elm
except ImportError:
    elm = None


if elm:
    class DummyGeneratedComponent(elm.Element):
        def __init__(self, *d, **kwargs):
            super().__init__(*d, **kwargs)
            self.segments.append(elm.Segment([(0, 0), (1, 1)]))


# Check if google-genai is installed at module level
genai_available = True
try:
    from google import genai as _genai_check
except ImportError:
    genai_available = False


def test_fallback_generate_component(monkeypatch):
    """Test LLM component generation with mocked genai client."""
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    import techfig.engines.fallback as fallback_mod

    # Save originals
    original_genai = fallback_mod.genai
    original_types = fallback_mod.types

    # Inject mock genai and types
    mock_genai = MagicMock()
    mock_types = MagicMock()
    fallback_mod.genai = mock_genai
    fallback_mod.types = mock_types

    if not elm:
        fallback_mod.elm = type('DummyElm', (), {'Element': object})

    try:
        # Set up mock response chain
        mock_response = MagicMock()
        mock_response.text = '''
```python
class CustomComponent(elm.Element):
    def __init__(self, *d, **kwargs):
        super().__init__(*d, **kwargs)
```
        '''

        mock_models = MagicMock()
        mock_models.generate_content.return_value = mock_response
        mock_client = MagicMock()
        mock_client.models = mock_models
        mock_genai.Client.return_value = mock_client

        comp_cls = fallback_mod.generate_component("Magic Hyperdrive")

        assert comp_cls is not None
        if elm:
            assert issubclass(comp_cls, elm.Element)
        assert comp_cls.__name__ == "Agentic_Magic_Hyperdrive"
    finally:
        fallback_mod.genai = original_genai
        fallback_mod.types = original_types


def test_fallback_no_api_key(monkeypatch):
    """generate_component should return None when GEMINI_API_KEY is not set."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    import techfig.engines.fallback as fallback_mod
    result = fallback_mod.generate_component("anything")
    assert result is None


def test_fallback_no_genai_package(monkeypatch):
    """generate_component should return None when google-genai is not installed."""
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    import techfig.engines.fallback as fallback_mod
    original_genai = fallback_mod.genai
    original_types = fallback_mod.types
    try:
        fallback_mod.genai = None
        fallback_mod.types = None
        result = fallback_mod.generate_component("anything")
        assert result is None
    finally:
        fallback_mod.genai = original_genai
        fallback_mod.types = original_types
