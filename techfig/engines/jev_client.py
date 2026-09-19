"""Jev client and review gate for TechFig.

Jev is TypeSafe's quality-review API: a classifier that returns typed
answers (scores, choices, nouls) for the ``state`` you submit.  It does not
generate code or figures — it returns signals the agent loop acts on.

Wire format (verified live against jev-1.13.0, 2026-09-19):

    POST https://api.typesafe.ai/v1/systemone
    Authorization: Bearer <JEV_API_KEY>
    {model, state, questions}

``questions`` is a dict keyed by answer name; each value is discriminated
by ``type``:

- ``score``   -> ``criteria`` = ordered list of 2-10 levels (index 0 lowest)
- ``choice``  -> ``criteria`` = dict of option -> description
- ``noul``    -> no criteria; a yes/no probability

Responses: ``answers`` keyed by name.  score -> {score, confidence, legend,
probabilities}; noul -> {noul}; choice -> {choice, confidence, probabilities}.

This module depends only on the stdlib.  The API key is read from
``JEV_API_KEY`` in the environment, falling back to ``~/.hermes/.env`` so the
client works inside herdr panes whose daemon was started without the key.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

JEV_API_URL = "https://api.typesafe.ai/v1/systemone"
DEFAULT_MODEL = "jev-latest"

# Fallback env file: the hermes .env.  Read only for the key name below.
_HERMES_ENV = Path.home() / ".hermes" / ".env"

# --------------------------------------------------------------------------
# Key handling
# --------------------------------------------------------------------------


def load_api_key() -> Optional[str]:
    """Return JEV_API_KEY from env, else from ~/.hermes/.env.  Never print it."""
    key = os.environ.get("JEV_API_KEY")
    if key:
        return key
    try:
        for line in _HERMES_ENV.read_text().splitlines():
            if line.startswith("JEV_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        return None
    return None


# --------------------------------------------------------------------------
# Question-set builder (scientist's v0 spec)
# --------------------------------------------------------------------------

# Ten ordered levels per core dimension; index 0 is the worst.
_CORE_DIMS: Dict[str, List[str]] = {
    "correctness": [
        "Broken; produces wrong output or a silent blank",
        "Severely wrong behavior on the main path",
        "Works on the happy path, wrong edge cases",
        "Mostly correct; one notable gap",
        "Correct on stated task; minor gaps",
        "Correct; edge cases handled",
        "Correct; error paths explicit",
        "Matches task; no silent failure modes",
        "Matches task; clean failure handling",
        "Fully correct; matches task exactly",
    ],
    "modularity": [
        "God-module diff; engine/CLI/tests entangled",
        "Module boundaries broken in the hot path",
        "Coupling added where seams existed",
        "Modules blurred but still separable",
        "Mostly separable; one weak seam",
        "Engines/CLI/tests stay separable",
        "Clean seams; no god-module growth",
        "New code lands in the right module",
        "Seams respected throughout",
        "Exemplary module boundaries",
    ],
    "changeability": [
        "Future edits require touching many sites",
        "Brittle coupling added",
        "Hard-coded values buried in the diff",
        "Change amplification without reason",
        "Acceptable seams; edits still cheap-ish",
        "Clear seams; local edits stay local",
        "Future edits cheap; no brittle coupling",
        "Config/data separated from logic",
        "Changeable; seams documented",
        "Changeable; edits are single-site",
    ],
    "security": [
        "Injection / path traversal / secret leak introduced",
        "Unescaped user input reaches output",
        "Unvalidated path escapes the workspace",
        "Secret or key material could leak",
        "Weak but present guards",
        "Inputs validated; no obvious leak",
        "Paths confined; output escaped",
        "No injection / path / secret vectors",
        "Defense in depth on all new surfaces",
        "Security clean; verifiable",
    ],
    "test_coverage": [
        "No tests; new path untested",
        "Tests do not exercise the change",
        "One smoke test; happy path only",
        "Tests cover main path",
        "Tests cover main path and one edge",
        "Fixtures exercise new behavior",
        "Tests land with the behavior",
        "Edge cases tested; fixtures real",
        "Coverage strong; regression-proof",
        "Exemplary test coverage",
    ],
    "reliability": [
        "Silent failure; empty or 277-byte SVG possible",
        "Failures swallowed",
        "Wrong exit code on failure",
        "Output non-empty not guaranteed",
        "Failure modes mostly explicit",
        "Exit codes set; errors surfaced",
        "Non-empty outputs enforced",
        "No silent blank-output path",
        "Reliable across formats",
        "Exemplary error handling",
    ],
    "compatibility": [
        "Breaks public CLI flags or schema enums",
        "DIAGRAM_SCHEMA enum out of lockstep",
        "diagrams.py and schema diverge",
        "Public API changed silently",
        "Mostly compatible; one drift",
        "Schema and engine in lockstep",
        "Public CLI flags stable",
        "No compatibility drift",
        "Compatibility verified across engines",
        "Exemplary compatibility",
    ],
}

# Gate nouls (probability of the YES reading).
_NOUL_GATES = [
    "safe_to_iterate",        # Safe to keep iterating the loop
    "needs_human_review",     # A human should look before merge
    "has_security_concern",   # Security risk introduced
]

_ROUTE_OPTIONS = {
    "iterate": "Safe to iterate further on the loop",
    "human": "Needs human review before continuing",
    "stop": "Loop is done; ship the result",
}


def build_questions(
    core_dims: Optional[Dict[str, List[str]]] = None,
    route: bool = True,
    instructions_extra: str = "",
) -> Dict[str, Any]:
    """Build the questions dict from scientist's v0 spec."""
    dims = core_dims if core_dims is not None else _CORE_DIMS
    questions: Dict[str, Any] = {}
    for name, levels in dims.items():
        if not (2 <= len(levels) <= 10):
            raise ValueError(f"dimension {name}: criteria must have 2-10 levels, got {len(levels)}")
        questions[name] = {
            "type": "score",
            "instructions": (
                f"How does this change score on {name}? "
                f"Higher index = better. {instructions_extra}".strip()
            ),
            "criteria": list(levels),
        }
    for gate in _NOUL_GATES:
        questions[gate] = {
            "type": "noul",
            "instructions": f"Does this change warrant: {gate.replace('_', ' ')}?",
        }
    if route:
        questions["route"] = {
            "type": "choice",
            "instructions": "What should the figure/code loop do next?",
            "criteria": dict(_ROUTE_OPTIONS),
        }
    return questions


# --------------------------------------------------------------------------
# Transport
# --------------------------------------------------------------------------


def post_review(
    state: Dict[str, Any],
    questions: Dict[str, Any],
    model: str = DEFAULT_MODEL,
    api_key: Optional[str] = None,
    timeout_s: float = 60.0,
) -> Dict[str, Any]:
    """POST {model, state, questions} to Jev.  Returns the parsed response.

    Raises RuntimeError on transport or HTTP errors; the message never
    contains the API key.
    """
    key = api_key if api_key is not None else load_api_key()
    if not key:
        raise RuntimeError(
            "JEV_API_KEY not found in env or ~/.hermes/.env; cannot call Jev."
        )
    payload = {"model": model, "state": state, "questions": questions}
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        JEV_API_URL,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        snippet = exc.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"Jev HTTP {exc.code}: {snippet}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Jev transport error: {exc.reason}") from exc
    return json.loads(raw)


# --------------------------------------------------------------------------
# Answer normalization + gating
# --------------------------------------------------------------------------


def scale_score(raw: float, n_levels: int) -> float:
    """Map a score position in [0, n_levels-1] to a 1-10 scale."""
    if n_levels <= 1:
        return round(raw, 2)
    return round(1.0 + raw * (9.0 / (n_levels - 1)), 2)


def normalize_answers(answers: Dict[str, Any]) -> Dict[str, Any]:
    """Return a flat dict: name -> normalized answer with scaled scores."""
    out: Dict[str, Any] = {}
    for name, ans in answers.items():
        typ = ans.get("type")
        if ans.get("applicable") is False:
            out[name] = {"type": typ, "applicable": False}
            continue
        if typ == "score":
            n = len(ans.get("legend", {}))
            out[name] = {
                "type": typ,
                "raw": ans.get("score"),
                "score": scale_score(ans.get("score", 0.0), n),
                "confidence": ans.get("confidence"),
                "legend": ans.get("legend"),
                "probabilities": ans.get("probabilities"),
            }
        elif typ == "noul":
            out[name] = {"type": typ, "noul": ans.get("noul")}
        elif typ == "choice":
            out[name] = {
                "type": typ,
                "choice": ans.get("choice"),
                "confidence": ans.get("confidence"),
                "probabilities": ans.get("probabilities"),
            }
        else:
            out[name] = ans
    return out


# Scientist's v0 thresholds — recalibrate after real probes.
V0_THRESHOLDS = {
    "hard_min_score": 6.0,          # any applicable core score below this -> hard fail
    "hard_correctness_min": 7.0,    # correctness below this (if applicable) -> hard fail
    "hard_security_concern": 0.6,   # has_security_concern noul >= this -> hard fail
    "pass_min_score": 7.0,          # all applicable core scores must be >= this to pass
    "pass_min_confidence": 0.5,     # score dims only (nouls carry no confidence)
    "pass_max_human": 0.5,          # needs_human_review noul < this to pass
    "pass_max_security": 0.4,       # has_security_concern noul < this to pass
}


def evaluate_gate(
    answers: Dict[str, Any],
    thresholds: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Apply the v0 gate to normalized answers.

    Returns {decision, reasons, scores}.  decision in
    {"pass", "hard_fail", "escalate"}.
    """
    t = {**V0_THRESHOLDS, **(thresholds or {})}
    reasons: List[str] = []
    scores: Dict[str, Any] = {}

    core = [n for n in _CORE_DIMS if n in answers]
    applicable_scores = []
    for name in core:
        ans = answers[name]
        if ans.get("applicable") is False:
            continue
        applicable_scores.append(name)
        scores[name] = {
            "score": ans.get("score"),
            "confidence": ans.get("confidence"),
        }

    sec = answers.get("has_security_concern", {}).get("noul")
    human = answers.get("needs_human_review", {}).get("noul")

    # --- hard fail ---
    for name in applicable_scores:
        sc = scores[name]["score"]
        if sc is not None and sc < t["hard_min_score"]:
            reasons.append(f"{name}: {sc} < {t['hard_min_score']} (hard min)")
    if applicable_scores and scores.get("correctness", {}).get("score") is not None:
        if scores["correctness"]["score"] < t["hard_correctness_min"]:
            reasons.append(
                f"correctness: {scores['correctness']['score']} < {t['hard_correctness_min']}"
            )
    if sec is not None and sec >= t["hard_security_concern"]:
        reasons.append(f"has_security_concern: {sec:.2f} >= {t['hard_security_concern']}")
    if reasons:
        return {"decision": "hard_fail", "reasons": reasons, "scores": scores}

    # --- escalate on low confidence / mixed signals ---
    for name in applicable_scores:
        conf = scores[name]["confidence"]
        if conf is not None and conf < t["pass_min_confidence"]:
            reasons.append(
                f"{name}: confidence {conf} < {t['pass_min_confidence']} (escalate)"
            )
    if reasons:
        return {"decision": "escalate", "reasons": reasons, "scores": scores}

    # --- pass gate ---
    for name in applicable_scores:
        sc = scores[name]["score"]
        if sc is not None and sc < t["pass_min_score"]:
            reasons.append(f"{name}: {sc} < {t['pass_min_score']} (pass min)")
    if human is not None and human >= t["pass_max_human"]:
        reasons.append(f"needs_human_review: {human:.2f} >= {t['pass_max_human']}")
    if sec is not None and sec >= t["pass_max_security"]:
        reasons.append(f"has_security_concern: {sec:.2f} >= {t['pass_max_security']}")

    if reasons:
        return {"decision": "hard_fail", "reasons": reasons, "scores": scores}
    return {"decision": "pass", "reasons": [], "scores": scores}


def diff_evals(previous: Dict[str, Any], current: Dict[str, Any]) -> Dict[str, Any]:
    """Per-answer deltas between two normalized answer dicts.

    Only meaningful for score answers (numeric).  Nouls/choices are reported
    as value changes.
    """
    deltas: Dict[str, Any] = {}
    for name, cur in current.items():
        prev = previous.get(name)
        if prev is None:
            deltas[name] = {"previous": None, "current": cur, "delta": None}
            continue
        if cur.get("type") == "score" and prev.get("type") == "score":
            p, c = prev.get("score"), cur.get("score")
            deltas[name] = {
                "previous": p,
                "current": c,
                "delta": None if (p is None or c is None) else round(c - p, 2),
            }
        else:
            deltas[name] = {
                "previous": prev,
                "current": cur,
                "delta": None,
            }
    return deltas


# --------------------------------------------------------------------------
# Action-picking question (Jev as the chooser in the de-collision loop)
# --------------------------------------------------------------------------


def build_action_question(
    candidates: List[Dict[str, Any]],
    instructions: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a single ``choice`` question mapping candidate ids -> moves.

    ``candidates`` is the ranked shortlist from
    ``layout_loop.rank_moves``.  The ``other`` option is always present so the
    model can decline rather than pick a hallucinated id.
    """
    if not candidates:
        raise ValueError("build_action_question requires at least one candidate")
    criteria = {c["id"]: c["description"] for c in candidates}
    criteria["other"] = "None of these: stop the loop"
    return {
        "action": {
            "type": "choice",
            "instructions": instructions or (
                "Choose the single option that leaves the FEWEST remaining "
                "shape overlaps; if two options tie on overlap count, choose "
                "the one with the HIGHEST geometry score. Prefer the smallest "
                "correction only when count and score are equal."
            ),
            "criteria": criteria,
        }
    }


def pick_action(
    state: Dict[str, Any],
    candidates: List[Dict[str, Any]],
    model: str = DEFAULT_MODEL,
    api_key: Optional[str] = None,
    timeout_s: float = 60.0,
) -> Dict[str, Any]:
    """Ask Jev to pick one candidate move.  Returns the raw choice + metadata.

    Does not map the id back to an action -- that is the caller's job (see
    ``layout_loop.make_jev_picker``).  ``choice`` may be ``"other"``/unknown.
    """
    questions = build_action_question(candidates)
    resp = post_review(state, questions, model=model, api_key=api_key,
                       timeout_s=timeout_s)
    answers = normalize_answers(resp.get("answers", {}))
    ans = answers.get("action", {})
    return {
        "choice": ans.get("choice"),
        "confidence": ans.get("confidence"),
        "probabilities": ans.get("probabilities"),
        "model": resp.get("model"),
        "usage": resp.get("usage"),
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _cli() -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="techfig-jev", description="Jev review gate for TechFig")
    ap.add_argument("--task", default="")
    ap.add_argument("--diff", default="")
    ap.add_argument("--files", nargs="*", default=[])
    ap.add_argument("--repo-context", default="")
    ap.add_argument("--previous", default="", help="path to previous evaluation JSON")
    ap.add_argument("--questions", default="", help="path to custom questions JSON")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    args = ap.parse_args()

    state: Dict[str, Any] = {
        "task": args.task,
        "diff": args.diff,
        "files": list(args.files),
        "repositoryContext": args.repo_context,
    }
    questions = (
        json.loads(Path(args.questions).read_text())
        if args.questions
        else build_questions()
    )
    resp = post_review(state, questions, model=args.model)
    answers = normalize_answers(resp.get("answers", {}))
    gate = evaluate_gate(answers)

    result = {
        "model": resp.get("model"),
        "usage": resp.get("usage"),
        "answers": answers,
        "gate": gate,
    }
    if args.previous:
        try:
            prev = json.loads(Path(args.previous).read_text())
            result["deltas"] = diff_evals(prev.get("answers", {}), answers)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"warning: could not read --previous: {exc}", file=sys.stderr)

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
