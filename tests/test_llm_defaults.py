"""Polish / auto-refine should default to a0 Grok, not Anthropic or Venice Qwen."""
import inspect

from techfig.utils.config import DEFAULT_CONFIG
from techfig.engines.sketch_interpreter import auto_refine, sketch_to_diagram
from techfig.engines.aesthetic_critic import score_aesthetic


def test_config_default_sketch_model_is_grok():
    assert DEFAULT_CONFIG["sketch_model"] == "openai/grok-4-6"


def test_auto_refine_defaults_to_grok():
    assert inspect.signature(auto_refine).parameters["model"].default == "openai/grok-4-6"


def test_sketch_to_diagram_defaults_to_grok():
    assert inspect.signature(sketch_to_diagram).parameters["model"].default == "openai/grok-4-6"


def test_score_aesthetic_defaults_to_grok():
    assert inspect.signature(score_aesthetic).parameters["model"].default == "openai/grok-4-6"


def test_llm_completion_kwargs_point_at_a0():
    from techfig.engines.llm_defaults import completion_kwargs, DEFAULT_API_BASE, DEFAULT_TEXT_MODEL

    assert DEFAULT_TEXT_MODEL == "openai/grok-4-6"
    assert "agent-zero" in DEFAULT_API_BASE
    kw = completion_kwargs()
    assert "api_base" in kw
    assert "agent-zero" in kw["api_base"]
