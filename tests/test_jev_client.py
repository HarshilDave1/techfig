"""Offline tests for jev_client — no network, no API key required."""

import json

import pytest

from techfig.engines import jev_client


def test_build_questions_has_all_dims():
    q = jev_client.build_questions()
    for dim in jev_client._CORE_DIMS:
        assert dim in q
        assert q[dim]["type"] == "score"
        assert 2 <= len(q[dim]["criteria"]) <= 10
    for gate in jev_client._NOUL_GATES:
        assert q[gate]["type"] == "noul"
    assert q["route"]["type"] == "choice"


def test_build_questions_rejects_bad_level_count():
    with pytest.raises(ValueError):
        jev_client.build_questions(core_dims={"x": ["only"]})


def test_scale_score():
    # 10 levels: raw 0 -> 1, raw 9 -> 10
    assert jev_client.scale_score(0.0, 10) == 1.0
    assert jev_client.scale_score(9.0, 10) == 10.0
    assert jev_client.scale_score(4.5, 10) == 5.5


def test_normalize_answers_score():
    ans = {
        "correctness": {
            "type": "score",
            "score": 8.4,
            "confidence": 0.9,
            "legend": {str(i): f"l{i}" for i in range(10)},
            "probabilities": {"9": 0.9},
        },
        "has_security_concern": {"type": "noul", "noul": 0.1},
        "route": {"type": "choice", "choice": "iterate", "confidence": 0.7},
    }
    norm = jev_client.normalize_answers(ans)
    assert norm["correctness"]["score"] == pytest.approx(1 + 8.4 * 9 / 9, rel=1e-6)
    assert norm["has_security_concern"]["noul"] == 0.1
    assert norm["route"]["choice"] == "iterate"


def test_normalize_answers_applicable_false():
    ans = {"security": {"type": "score", "applicable": False}}
    norm = jev_client.normalize_answers(ans)
    assert norm["security"]["applicable"] is False


def _perfect_answers():
    norm = {}
    for dim, levels in jev_client._CORE_DIMS.items():
        norm[dim] = {
            "type": "score",
            "raw": len(levels) - 1,
            "score": 10.0,
            "confidence": 0.95,
        }
    norm["has_security_concern"] = {"type": "noul", "noul": 0.05}
    norm["needs_human_review"] = {"type": "noul", "noul": 0.1}
    norm["safe_to_iterate"] = {"type": "noul", "noul": 0.95}
    return norm


def test_gate_pass():
    gate = jev_client.evaluate_gate(_perfect_answers())
    assert gate["decision"] == "pass"
    assert gate["reasons"] == []


def test_gate_hard_fail_low_score():
    answers = _perfect_answers()
    answers["correctness"]["score"] = 5.5
    gate = jev_client.evaluate_gate(answers)
    assert gate["decision"] == "hard_fail"
    assert any("correctness" in r for r in gate["reasons"])


def test_gate_hard_fail_security():
    answers = _perfect_answers()
    answers["has_security_concern"]["noul"] = 0.8
    gate = jev_client.evaluate_gate(answers)
    assert gate["decision"] == "hard_fail"


def test_gate_escalate_low_confidence():
    answers = _perfect_answers()
    answers["modularity"]["confidence"] = 0.3
    gate = jev_client.evaluate_gate(answers)
    assert gate["decision"] == "escalate"


def test_diff_evals():
    prev = _perfect_answers()
    cur = {k: dict(v) for k, v in prev.items()}
    cur["correctness"]["score"] = 9.0
    deltas = jev_client.diff_evals(prev, cur)
    assert deltas["correctness"]["delta"] == pytest.approx(-1.0)


def test_cli_shape_roundtrip():
    """CLI JSON we emit can be re-read for previousEvaluation deltas."""
    gate = jev_client.evaluate_gate(_perfect_answers())
    blob = json.dumps({"answers": _perfect_answers(), "gate": gate})
    loaded = json.loads(blob)
    assert loaded["gate"]["decision"] == "pass"


# --------------------------------------------------------------------------
# Action picking (Jev as the chooser in the de-collision loop)
# --------------------------------------------------------------------------


def test_build_action_question_maps_candidates():
    cands = [
        {"id": "m1", "description": "Move 'a' 80 right"},
        {"id": "m2", "description": "Move 'b' 40 down"},
    ]
    q = jev_client.build_action_question(cands)
    assert q["action"]["type"] == "choice"
    assert q["action"]["criteria"] == {
        "m1": "Move 'a' 80 right",
        "m2": "Move 'b' 40 down",
        "other": "None of these: stop the loop",
    }


def test_build_action_question_requires_candidates():
    with pytest.raises(ValueError):
        jev_client.build_action_question([])


def test_pick_action_returns_choice_and_meta(monkeypatch):
    def fake_post(state, questions, **kwargs):
        assert "action" in questions
        assert questions["action"]["type"] == "choice"
        return {
            "model": "jev-test",
            "answers": {
                "action": {
                    "type": "choice",
                    "choice": "m2",
                    "confidence": 0.81,
                    "probabilities": {"m1": 0.1, "m2": 0.81, "other": 0.09},
                }
            },
            "usage": {"input_tokens": 10, "output_tokens": 2},
        }

    monkeypatch.setattr(jev_client, "post_review", fake_post)
    out = jev_client.pick_action(
        {"shapes": [], "overlaps": []},
        [{"id": "m1", "description": "a"}, {"id": "m2", "description": "b"}],
    )
    assert out["choice"] == "m2"
    assert out["confidence"] == 0.81
    assert out["model"] == "jev-test"
