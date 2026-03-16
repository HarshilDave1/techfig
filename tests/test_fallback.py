import pytest
from unittest.mock import patch, MagicMock
from techfig.engines.fallback import generate_component
try:
    import schemdraw.elements as elm
except ImportError:
    elm = None


if elm:
    class DummyGeneratedComponent(elm.Element):
        def __init__(self, *d, **kwargs):
            super().__init__(*d, **kwargs)
            # Just a dummy segment
            self.segments.append(elm.Segment([(0, 0), (1, 1)]))


@patch("techfig.engines.fallback.genai.Client")
def test_fallback_generate_component(mock_client_class, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    
    import techfig.engines.fallback as fallback_mod
    
    if not elm:
        # Inject dummy elm into module to avoid NameError during test
        fallback_mod.elm = type('DummyElm', (), {'Element': object})

    mock_client = MagicMock()
    mock_response = MagicMock()
    
    # We supply valid python code that creates a CustomComponent
    mock_response.text = '''
```python
class CustomComponent(elm.Element):
    def __init__(self, *d, **kwargs):
        super().__init__(*d, **kwargs)
```
    '''
    
    mock_client.models.generate_content.return_value = mock_response
    mock_client_class.return_value = mock_client
    
    comp_cls = generate_component("Magic Hyperdrive")
    
    assert comp_cls is not None
    if elm:
        assert issubclass(comp_cls, elm.Element)
    assert comp_cls.__name__ == "Agentic_Magic_Hyperdrive"
