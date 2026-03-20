"""The AutoResearch Loop Runner orchestration engine.

Analogous to Karpathy's autoresearch, but for diagram generation.
It coordinates the modify -> render -> evaluate -> keep/discard lifecycle.
"""

import os
import copy
import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple
from dataclasses import dataclass

from techfig.engines.geo_linter import score_geometry, lint_spec
from techfig.engines.aesthetic_critic import score_aesthetic
from techfig.engines.sketch_interpreter import render_from_spec

@dataclass
class Experiment:
    """A record of one iteration of the autoresearch loop."""
    generation: int
    spec: Dict[str, Any]
    svg_path: str
    geo_score: float
    aesthetic_score: float
    total_score: float
    feedback: str
    kept: bool

class AutoResearchLoop:
    """Autonomous diagram improvement loop."""
    
    def __init__(
        self,
        initial_spec: Dict[str, Any],
        output_dir: str,
        reference_image_path: Optional[str] = None,
        max_rounds: int = 5,
        geo_weight: float = 0.5,
        aesthetic_weight: float = 0.5,
        vision_model: str = "claude-3-5-sonnet-20241022"
    ):
        self.initial_spec = copy.deepcopy(initial_spec)
        self.output_dir = output_dir
        self.reference_image_path = reference_image_path
        self.max_rounds = max_rounds
        self.geo_weight = geo_weight
        self.aesthetic_weight = aesthetic_weight
        self.vision_model = vision_model
        
        self.history: List[Experiment] = []
        os.makedirs(self.output_dir, exist_ok=True)
        
    def _evaluate(self, spec: Dict[str, Any], gen: int) -> Tuple[str, float, float, float, str]:
        """Renders and scores a spec."""
        svg_filename = f"gen_{gen}.svg"
        svg_path = os.path.join(self.output_dir, svg_filename)
        
        # Fixed budget "training": rendering the SVG
        render_from_spec(spec, svg_path)
        
        # 1. Geo Score
        geo_report = lint_spec(spec)
        geo_score = geo_report.score
        
        # 2. Aesthetic Score
        aes_score, aes_feedback = score_aesthetic(
            svg_path,
            model=self.vision_model,
            reference_image_path=self.reference_image_path
        )
        
        # Compose score
        total_score = (geo_score * self.geo_weight) + (aes_score * self.aesthetic_weight)
        
        # Construct combined feedback string for the agent
        issues = geo_report.alignment_issues + geo_report.grid_issues + geo_report.overlap_issues
        geo_feedback = "Geometric Issues to fix:\n- " + "\n- ".join(issues) if issues else "No major geometric issues detected."
        
        combined_feedback = f"{geo_feedback}\n\nVisual/Aesthetic Feedback:\n{aes_feedback}"
        
        return svg_path, geo_score, aes_score, total_score, combined_feedback
        
    def run(self, mutator_fn: Callable[[Dict[str, Any], str], Dict[str, Any]]) -> Dict[str, Any]:
        """Execute the autoresearch loop.
        
        mutator_fn receives the current best spec (dict) and the feedback string,
        and should return a modified spec.
        """
        print(f"Starting autoresearch loop in {self.output_dir} for {self.max_rounds} rounds.")
        
        # Baseline
        best_spec = copy.deepcopy(self.initial_spec)
        try:
            svg_path, geo_s, aes_s, total_s, feedback = self._evaluate(best_spec, 0)
        except Exception as e:
            print(f"Failed to evaluate initial spec: {e}")
            # If initial spec is utterly broken, we can't score it properly. 
            # We'll assign a 0 score and empty feedback.
            svg_path, geo_s, aes_s, total_s, feedback = "", 0.0, 0.0, 0.0, str(e)
            
        best_score = total_s
        
        exp = Experiment(0, best_spec, svg_path, geo_s, aes_s, total_s, feedback, kept=True)
        self.history.append(exp)
        
        print(f"Gen 0 | Geo: {geo_s:.2f} | Aes: {aes_s:.2f} | Total: {total_s:.2f} | *Base*")
        
        last_feedback = feedback
        
        for gen in range(1, self.max_rounds + 1):
            try:
                candidate = mutator_fn(copy.deepcopy(best_spec), last_feedback)
                c_svg_path, c_geo_s, c_aes_s, c_total_s, c_feedback = self._evaluate(candidate, gen)
                
                kept = False
                if c_total_s > best_score:
                    best_spec = candidate
                    best_score = c_total_s
                    last_feedback = c_feedback
                    kept = True
                    mark = "✓ KEPT"
                else:
                    # Provide feedback on why it was rejected so the LLM knows it failed
                    last_feedback = (
                        f"PREVIOUS MUTATION REJECTED (Score {c_total_s:.2f} was not > {best_score:.2f}).\n"
                        f"Validation of the rejected candidate:\n{c_feedback}\n\n"
                        f"Try a DIFFERENT approach to fix the previous baseline issues."
                    )
                    mark = "✗ REJECTED"
                
                exp = Experiment(gen, candidate, c_svg_path, c_geo_s, c_aes_s, c_total_s, c_feedback, kept)
                self.history.append(exp)
                
                print(f"Gen {gen} | Geo: {c_geo_s:.2f} | Aes: {c_aes_s:.2f} | Total: {c_total_s:.2f} | {mark}")
                
            except Exception as e:
                print(f"Gen {gen} Failed during mutation/rendering: {e}")
                last_feedback = f"FATAL ERROR in previous mutation: {e}\nReverting to previous best spec and trying again."
                
        # Write experiment log summary
        log_path = os.path.join(self.output_dir, "experiment_log.json")
        with open(log_path, "w") as f:
            log_data = []
            for e in self.history:
                log_data.append({
                    "generation": e.generation,
                    "geo_score": e.geo_score,
                    "aesthetic_score": e.aesthetic_score,
                    "total_score": e.total_score,
                    "kept": e.kept,
                    "svg_path": e.svg_path
                })
            json.dump(log_data, f, indent=2)
            
        print(f"\nBest Score: {best_score:.2f}")
        return best_spec
