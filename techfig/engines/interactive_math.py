"""Interactive SymPy math widget engine.

Generates interactive HTML documents containing symbolic math
equations (using SymPy) that can be manipulated by the viewer
via sliders or inputs.
"""
import logging
import json
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

def create_math_widget(
    equation_str: str,
    output_path: str,
    variables: List[Dict[str, Any]],
    title: str = "Interactive Math Widget",
    description: str = ""
) -> str:
    """Create an interactive HTML math widget using SymPy and MathJax.
    
    Args:
        equation_str: A Python expression string representing the equation
            (e.g., "A * sin(omega * t + phi)").
        output_path: Where to save the interactive HTML file.
        variables: List of variable definitions for sliders. Each dict should have:
            - name: The variable name in the equation
            - label: Display label
            - min: Minimum value (default 0)
            - max: Maximum value (default 10)
            - step: Step size (default 0.1)
            - value: Initial value (default min)
        title: Title of the widget.
        description: Text description or instructions below the title.
        
    Returns:
        The absolute path to the generated HTML file.
    """
    # Create HTML structure with MathJax for rendering and minimal JS for reactivity
    
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>{title}</title>
    <script src="https://polyfill.io/v3/polyfill.min.js?features=es6"></script>
    <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/mathjs/11.8.0/math.js"></script>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 2rem;
            background-color: #f8fafc;
            color: #0f172a;
        }}
        .card {{
            background: white;
            border-radius: 8px;
            padding: 2rem;
            box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1);
        }}
        h1 {{ margin-top: 0; color: #1e293b; }}
        .description {{ color: #64748b; margin-bottom: 2rem; }}
        .equation-display {{
            font-size: 1.5rem;
            padding: 2rem;
            background: #f1f5f9;
            border-radius: 8px;
            text-align: center;
            margin-bottom: 2rem;
            overflow-x: auto;
        }}
        .controls {{
            display: grid;
            gap: 1.5rem;
        }}
        .control-group {{
            display: flex;
            align-items: center;
            gap: 1rem;
        }}
        .control-group label {{
            min-width: 80px;
            font-weight: 600;
        }}
        .control-group input[type=range] {{
            flex: 1;
        }}
        .val-display {{
            min-width: 60px;
            text-align: right;
            font-variant-numeric: tabular-nums;
        }}
        .result-display {{
            margin-top: 2rem;
            padding-top: 2rem;
            border-top: 1px solid #e2e8f0;
            font-size: 1.25rem;
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="card">
        <h1>{title}</h1>
        {f'<p class="description">{description}</p>' if description else ''}
        
        <div class="equation-display">
            \\[ f = {equation_str} \\]
        </div>
        
        <div class="controls" id="controls">
            <!-- Controls injected by JS -->
        </div>
        
        <div class="result-display">
            Result = <span id="result-val">0.000</span>
        </div>
    </div>

    <script>
        const equation = "{equation_str}";
        const variables = {json.dumps(variables)};
        
        // Compile the equation with math.js
        const compiledEq = math.compile(equation);
        
        // Current state
        const state = {{}};
        
        function updateResult() {{
            try {{
                const res = compiledEq.evaluate(state);
                document.getElementById('result-val').innerText = Number(res).toFixed(4);
            }} catch (e) {{
                document.getElementById('result-val').innerText = "Error";
                console.error(e);
            }}
        }}
        
        const controlsDiv = document.getElementById('controls');
        
        variables.forEach(v => {{
            // Set initial state
            const initVal = v.value !== undefined ? v.value : (v.min || 0);
            state[v.name] = initVal;
            
            const group = document.createElement('div');
            group.className = 'control-group';
            
            const label = document.createElement('label');
            label.innerHTML = `\\(${{v.label || v.name}}\\)`;
            
            const slider = document.createElement('input');
            slider.type = 'range';
            slider.min = v.min || 0;
            slider.max = v.max || 10;
            slider.step = v.step || 0.1;
            slider.value = initVal;
            
            const valDisplay = document.createElement('div');
            valDisplay.className = 'val-display';
            valDisplay.innerText = initVal;
            
            slider.oninput = (e) => {{
                const val = parseFloat(e.target.value);
                state[v.name] = val;
                valDisplay.innerText = val.toFixed(2);
                updateResult();
            }};
            
            group.appendChild(label);
            group.appendChild(slider);
            group.appendChild(valDisplay);
            controlsDiv.appendChild(group);
        }});
        
        // Initial render
        updateResult();
        
        // Typeset mathjax for dynamically added labels
        setTimeout(() => {{
            if (window.MathJax) {{
                MathJax.typesetPromise();
            }}
        }}, 100);
    </script>
</body>
</html>"""

    out_file = Path(output_path).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)
    
    if out_file.suffix != ".html":
        out_file = out_file.with_suffix(".html")
        
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(html_content)
        
    return str(out_file)
