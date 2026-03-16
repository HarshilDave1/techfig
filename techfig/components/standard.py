"""Standard component library with schemdraw integration.

This module provides access to built-in scientific diagram components
from schemdraw (electrical circuits) and custom physics components.

Components are organized by category and can be rendered to SVG.
"""
from __future__ import annotations

from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
import tempfile

from techfig.components.registry import (
    ComponentRegistry,
    ComponentMeta,
    ComponentCategory,
    get_registry,
)

# Import schemdraw elements
try:
    import schemdraw
    import schemdraw.elements as elm
    SCHEMDRAW_AVAILABLE = True
except ImportError:
    SCHEMDRAW_AVAILABLE = False


# Mapping of component names to schemdraw element classes
SCHEMDRAW_ELEMENTS = {
    # Circuit - Basic
    "resistor": ("elm.Resistor", ComponentCategory.CIRCUIT, ["R", "resistance", "electrical"]),
    "capacitor": ("elm.Capacitor", ComponentCategory.CIRCUIT, ["C", "capacitance", "electrical"]),
    "inductor": ("elm.Inductor", ComponentCategory.CIRCUIT, ["L", "inductance", "coil", "electrical"]),
    "diode": ("elm.Diode", ComponentCategory.CIRCUIT, ["D", "rectifier", "electrical"]),
    "led": ("elm.LED", ComponentCategory.CIRCUIT, ["light emitting diode", "electrical"]),
    "zener": ("elm.Zener", ComponentCategory.CIRCUIT, ["zener diode", "electrical"]),
    "fuse": ("elm.Fuse", ComponentCategory.CIRCUIT, ["protection", "electrical"]),

    # Circuit - Sources
    "battery": ("elm.Battery", ComponentCategory.CIRCUIT, ["voltage source", "DC", "electrical"]),
    "cell": ("elm.Cell", ComponentCategory.CIRCUIT, ["battery cell", "electrical"]),
    "source": ("elm.Source", ComponentCategory.CIRCUIT, ["voltage source", "electrical"]),
    "source_v": ("elm.SourceV", ComponentCategory.CIRCUIT, ["voltage source", "electrical"]),
    "source_i": ("elm.SourceI", ComponentCategory.CIRCUIT, ["current source", "electrical"]),
    "source_sin": ("elm.SourceSin", ComponentCategory.CIRCUIT, ["AC source", "sinusoidal", "electrical"]),

    # Circuit - Switches
    "switch": ("elm.Switch", ComponentCategory.CIRCUIT, ["switch spst", "electrical"]),
    "switch_spdt": ("elm.SwitchSpdt2", ComponentCategory.CIRCUIT, ["double throw", "electrical"]),
    "button": ("elm.Button", ComponentCategory.CIRCUIT, ["push button", "electrical"]),

    # Circuit - Ground & Connections
    "ground": ("elm.Ground", ComponentCategory.CIRCUIT, ["gnd", "earth", "electrical"]),
    "ground_chassis": ("elm.GroundChassis", ComponentCategory.CIRCUIT, ["chassis ground", "electrical"]),
    "dot": ("elm.Dot", ComponentCategory.CIRCUIT, ["connection", "junction", "electrical"]),
    "line": ("elm.Line", ComponentCategory.CIRCUIT, ["wire", "connection", "electrical"]),

    # Circuit - Meters
    "meter_v": ("elm.MeterV", ComponentCategory.CIRCUIT, ["voltmeter", "electrical"]),
    "meter_i": ("elm.MeterI", ComponentCategory.CIRCUIT, ["ammeter", "electrical"]),

    # Circuit - Transistors
    "nfet": ("elm.NFet", ComponentCategory.CIRCUIT, ["n-channel fet", "transistor", "electrical"]),
    "pfet": ("elm.PFet", ComponentCategory.CIRCUIT, ["p-channel fet", "transistor", "electrical"]),
    "nmos": ("elm.NMOS", ComponentCategory.CIRCUIT, ["nmos transistor", "electrical"]),
    "pmos": ("elm.PMOS", ComponentCategory.CIRCUIT, ["pmos transistor", "electrical"]),
    "npn": ("elm.BjtNpn", ComponentCategory.CIRCUIT, ["bjt", "transistor", "electrical"]),
    "pnp": ("elm.BjtPnp", ComponentCategory.CIRCUIT, ["bjt", "transistor", "electrical"]),

    # Circuit - Op-Amps
    "opamp": ("elm.Opamp", ComponentCategory.CIRCUIT, ["operational amplifier", "electrical"]),
    "opamp_nosmap": ("elm.OpampNonist", ComponentCategory.CIRCUIT, ["opamp no swap", "electrical"]),

    # Circuit - Misc
    "lamp": ("elm.Lamp", ComponentCategory.CIRCUIT, ["light bulb", "electrical"]),
    "speaker": ("elm.Speaker", ComponentCategory.CIRCUIT, ["audio", "electrical"]),
    "mic": ("elm.Mic", ComponentCategory.CIRCUIT, ["microphone", "audio", "electrical"]),
    "antenna": ("elm.Antenna", ComponentCategory.CIRCUIT, ["aerial", "rf", "electrical"]),
}


def _get_schemdraw_element(element_path: str):
    """Dynamically get schemdraw element class from string path."""
    if not SCHEMDRAW_AVAILABLE:
        return None

    if element_path.startswith("generated."):
        # We can't easily re-hydrate generated classes cross-session right now
        # without saving the code. For now, generated components only live 
        # in the current memory process.
        return None

    parts = element_path.split(".")
    if len(parts) != 2:
        return None

    module_name, class_name = parts
    if module_name == "elm":
        return getattr(elm, class_name, None)
    return None


def load_standard_components(registry: Optional[ComponentRegistry] = None) -> int:
    """Load all standard schemdraw components into the registry.

    Args:
        registry: Registry to load into. Uses global registry if None.

    Returns:
        Number of components loaded.
    """
    if registry is None:
        registry = get_registry()

    loaded = 0
    for name, (element_path, category, tags) in SCHEMDRAW_ELEMENTS.items():
        element_cls = _get_schemdraw_element(element_path)
        if element_cls is None:
            continue

        # Create friendly description
        desc = f"{name.replace('_', ' ').title()} component from schemdraw"

        meta = ComponentMeta(
            name=name,
            category=category,
            source="standard",
            tags=tags,
            description=desc,
            schemdraw_element=element_path,
        )
        registry.register(meta)
        loaded += 1

    return loaded


def render_schemdraw_component(
    component_name: str,
    output_path: Optional[str] = None,
    allow_fallback: bool = False,
    **kwargs
) -> Optional[str]:
    """Render a schemdraw component to SVG.

    Args:
        component_name: Name of the component (e.g., "resistor", "capacitor")
        output_path: Where to save the SVG. If None, returns SVG string.
        allow_fallback: Whether to attempt generating missing components via LLM.
        **kwargs: Additional arguments for the element (label, value, etc.)

    Returns:
        SVG string if output_path is None, otherwise file path.
    """
    if not SCHEMDRAW_AVAILABLE:
        raise ImportError("schemdraw is not installed")

    registry = get_registry()
    meta = registry.get(component_name)

    if meta is None or meta.schemdraw_element is None:
        if allow_fallback:
            import logging
            from techfig.engines.fallback import generate_component
            logger = logging.getLogger(__name__)
            logger.info(f"Component '{component_name}' not found. Attempting agentic fallback...")
            element_cls = generate_component(component_name)
            if element_cls is None:
                raise ValueError(f"Unknown schemdraw component and fallback generation failed: {component_name}")
            
            # Register it for future use in this run
            desc = f"Dynamically generated {component_name} component"
            meta = ComponentMeta(
                name=component_name,
                category=ComponentCategory.CUSTOM,
                source="generated",
                tags=["generated", component_name],
                description=desc,
                schemdraw_element=f"generated.{element_cls.__name__}",
            )
            registry.register(meta)
        else:
            raise ValueError(f"Unknown schemdraw component: {component_name}")
    else:
        element_cls = _get_schemdraw_element(meta.schemdraw_element)
        if element_cls is None:
            raise ValueError(f"Cannot load schemdraw element: {meta.schemdraw_element}")

    # Create element with arguments
    element = element_cls(**kwargs)

    # Create drawing and add element
    with schemdraw.Drawing(file=output_path) as d:
        d += element

    if output_path:
        return output_path
    else:
        # Return as SVG string
        with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as tmp:
            tmp_path = tmp.name

        with schemdraw.Drawing(file=tmp_path) as d:
            d += element

        with open(tmp_path, "r") as f:
            svg_content = f.read()

        Path(tmp_path).unlink()
        return svg_content


def create_circuit(
    components: List[Dict[str, Any]],
    connections: List[Dict[str, Any]],
    output_path: str,
    **drawing_kwargs
) -> str:
    """Create a circuit diagram by connecting multiple components.

    Args:
        components: List of component dicts with keys:
            - name: component name (e.g., "resistor")
            - label: optional label text
            - id: unique identifier for connections
        connections: List of connection dicts with keys:
            - from: source component id
            - to: target component id
            - direction: "right", "down", "left", "up" (default: "right")
        output_path: Where to save the SVG.
        **drawing_kwargs: Arguments for schemdraw.Drawing

    Returns:
        Path to the generated SVG file.
    """
    if not SCHEMDRAW_AVAILABLE:
        raise ImportError("schemdraw is not installed")

    registry = get_registry()
    element_map: Dict[str, Any] = {}

    with schemdraw.Drawing(file=output_path, **drawing_kwargs) as d:
        for comp in components:
            meta = registry.get(comp["name"])
            if meta is None or meta.schemdraw_element is None:
                raise ValueError(f"Unknown component: {comp['name']}")

            element_cls = _get_schemdraw_element(meta.schemdraw_element)
            if element_cls is None:
                continue

            # Build kwargs for this element
            elem_kwargs = {}
            if "label" in comp:
                elem_kwargs["label"] = comp["label"]

            element = element_cls(**elem_kwargs)
            element_map[comp["id"]] = element
            d += element

        # Process connections (schemdraw handles this through element chaining)
        for conn in connections:
            from_elem = element_map.get(conn["from"])
            to_elem = element_map.get(conn["to"])

            if from_elem and to_elem:
                direction = conn.get("direction", "right")
                # Note: schemdraw handles connections through element placement
                # This is simplified - more complex routing would need additional logic

    return output_path


def list_available_components() -> List[str]:
    """List all available standard component names."""
    return list(SCHEMDRAW_ELEMENTS.keys())


def is_schemdraw_available() -> bool:
    """Check if schemdraw is available."""
    return SCHEMDRAW_AVAILABLE
