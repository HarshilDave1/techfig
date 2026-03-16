"""Component library for TechFig diagrams.

This module provides a unified interface for diagram components:

- **Standard Library**: Schemdraw elements for electrical circuits and physics diagrams
- **Lab Folder**: User-defined custom SVG/PNG components
- **Registry**: Unified component search and retrieval

Quick start:
    from techfig.components import get_registry, load_standard_components
    
    # Initialize and load components
    registry = get_registry()
    load_standard_components(registry)
    
    # Search for components
    resistors = registry.search("resistor")
    
    # Render a component
    from techfig.components import render_schemdraw_component
    svg = render_schemdraw_component("resistor", label="R1")
"""
from techfig.components.registry import (
    ComponentRegistry,
    ComponentMeta,
    ComponentCategory,
    get_registry,
    reset_registry,
)
from techfig.components.standard import (
    load_standard_components,
    render_schemdraw_component,
    create_circuit,
    list_available_components,
    is_schemdraw_available,
)
from techfig.components.lab_folder import (
    LabFolder,
    get_lab_folder,
)

__all__ = [
    # Registry
    "ComponentRegistry",
    "ComponentMeta", 
    "ComponentCategory",
    "get_registry",
    "reset_registry",
    # Standard library
    "load_standard_components",
    "render_schemdraw_component",
    "create_circuit",
    "list_available_components",
    "is_schemdraw_available",
    # Lab folder
    "LabFolder",
    "get_lab_folder",
]
