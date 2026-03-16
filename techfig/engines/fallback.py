import os
import json
import logging
from typing import Optional, Dict, Any, Type
try:
    import schemdraw.elements as elm
except ImportError:
    elm = None
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

# The prompt uses a structured output to constrain the LLM 
# to providing a class definition we can inject reliably.
FALLBACK_PROMPT = """
You are an expert Python engineer and Schemdraw library user.
The user has requested a diagram component named "{component_name}" that is not currently in the standard library.

Your task is to write a Python script that defines a Schemdraw Element subclass for this component.

Requirements:
1. The class MUST be named `CustomComponent`.
2. The class MUST inherit from `schemdraw.elements.Element` or a suitable subclass (e.g., `Element2Term`).
3. You must use standard Schemdraw drawing commands in the `__init__` method (e.g., `self.segments.append(...)`). 
4. The component should mathematically look like a real `{component_name}`.
5. Provide anchors if relevant.

Return ONLY the raw python code. Do not wrap in markdown blocks like ```python. 

Example:
import schemdraw.elements as elm
from schemdraw.segments import Segment, SegmentCircle

class CustomComponent(elm.Element2Term):
    def __init__(self, *d, **kwargs):
        super().__init__(*d, **kwargs)
        self.segments.append(Segment([(0, 0), (1, 1)]))
"""

def generate_component(name: str) -> Optional[Type[Any]]:
    """
    Given a component name, use an LLM to generate the Python code 
    defining a Schemdraw Element subclass representing it.
    
    Dynamically executes the script and returns the class if successful.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.warning(
            "GEMINI_API_KEY environment variable not set. "
            "Cannot use agentic fallback for component generation."
        )
        return None
        
    try:
        client = genai.Client()
        prompt = FALLBACK_PROMPT.format(component_name=name)
        
        logger.info(f"Querying Gemini to generate custom component: {name}")
        response = client.models.generate_content(
            model='gemini-2.5-pro',
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
            )
        )
        
        code = response.text
        # robustly strip markdown blocks if they exist
        lines = code.strip().split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
            
        code = "\n".join(lines).strip()
        logger.debug(f"Generated code for {name}:\n{code}")
        
        # We need a safe local namespace to execute the generated code
        local_scope = {}
        # Provide common imports the LLM might use
        global_scope = {
            "__builtins__": __builtins__
        }
        if elm:
            global_scope["elm"] = elm

        
        # Execute the code
        exec(code, global_scope, local_scope)
        
        # Extract the class
        if "CustomComponent" in local_scope:
            custom_cls = local_scope["CustomComponent"]
            # Rename it to make debugging easier later
            custom_cls.__name__ = f"Agentic_{name.replace(' ', '_').title()}"
            return custom_cls
        else:
            logger.error(f"LLM failed to generate a 'CustomComponent' class for {name}.")
            return None
            
    except Exception as e:
        logger.error(f"Failed to generate component '{name}' via LLM: {e}")
        return None
