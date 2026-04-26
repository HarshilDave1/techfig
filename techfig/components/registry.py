"""Component registry for managing reusable diagram elements.

This module provides a unified registry that combines:
- Standard library components (schemdraw physics/circuits)
- Lab folder components (user-defined SVG/PNG files)
- Dynamic component generation

The registry supports indexing, search, and retrieval of components
by name, category, or tags.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict
from enum import Enum


class ComponentCategory(Enum):
    """Categories for organizing components."""
    CIRCUIT = "circuit"
    PHYSICS = "physics"  
    OPTICS = "optics"
    MECHANICS = "mechanics"
    CHEMISTRY = "chemistry"
    BIOLOGY = "biology"
    FLOWCHART = "flowchart"
    CUSTOM = "custom"


@dataclass
class ComponentMeta:
    """Metadata for a registered component."""
    name: str
    category: ComponentCategory
    source: str  # "standard", "lab_folder", "generated"
    tags: List[str] = field(default_factory=list)
    description: str = ""
    file_path: Optional[str] = None  # For lab_folder components
    schemdraw_element: Optional[str] = None  # For standard components
    created_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["category"] = self.category.value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ComponentMeta":
        data = data.copy()
        data["category"] = ComponentCategory(data["category"])
        return cls(**data)


class ComponentRegistry:
    """Unified registry for all diagram components.

    Components are loaded from:
    1. Standard library (schemdraw elements)
    2. Lab folder (~/.techfig/components)
    3. Dynamic generation (LLM-created SVG)

    Example usage:
        registry = ComponentRegistry()
        registry.load_standard_components()
        registry.load_lab_folder()

        # Search for components
        matches = registry.search("resistor")

        # Get component for rendering
        element = registry.get_element("resistor")
    """

    DEFAULT_LAB_FOLDER = Path.home() / ".techfig" / "components"
    INDEX_FILE = "index.json"

    def __init__(self, lab_folder: Optional[Path] = None):
        self._components: Dict[str, ComponentMeta] = {}
        self._aliases: Dict[str, str] = {}  # alias -> canonical name
        self._lab_folder = lab_folder or self.DEFAULT_LAB_FOLDER
        self._lab_folder.mkdir(parents=True, exist_ok=True)

    @property
    def lab_folder(self) -> Path:
        return self._lab_folder

    def register(self, component: ComponentMeta) -> None:
        """Register a component. Updates existing if name exists."""
        self._components[component.name.lower()] = component
        # Add common aliases
        self._aliases[component.name.lower()] = component.name.lower()
        for tag in component.tags:
            self._aliases[tag.lower()] = component.name.lower()

    def unregister(self, name: str) -> bool:
        """Remove a component from the registry."""
        key = name.lower()
        if key in self._components:
            del self._components[key]
            # Clean up aliases
            self._aliases = {k: v for k, v in self._aliases.items() if v != key}
            return True
        return False

    def get(self, name: str) -> Optional[ComponentMeta]:
        """Get component metadata by name or alias."""
        key = self._aliases.get(name.lower(), name.lower())
        return self._components.get(key)

    def search(self, query: str, category: Optional[ComponentCategory] = None) -> List[ComponentMeta]:
        """Search components by name, tags, or description."""
        query = query.lower()
        results = []

        for comp in self._components.values():
            if category and comp.category != category:
                continue

            # Match against name, tags, description
            if (query in comp.name.lower() or
                any(query in tag for tag in comp.tags) or
                query in comp.description.lower()):
                results.append(comp)

        return results

    def list_all(self, category: Optional[ComponentCategory] = None) -> List[ComponentMeta]:
        """List all registered components, optionally filtered by category."""
        if category:
            return [c for c in self._components.values() if c.category == category]
        return list(self._components.values())

    def list_categories(self) -> Dict[ComponentCategory, int]:
        """Get count of components per category."""
        counts: Dict[ComponentCategory, int] = {}
        for comp in self._components.values():
            counts[comp.category] = counts.get(comp.category, 0) + 1
        return counts

    def save_index(self) -> None:
        """Save the registry index to the lab folder."""
        index_path = self._lab_folder / self.INDEX_FILE
        data = {
            "version": "1.0",
            "components": {name: comp.to_dict() for name, comp in self._components.items()}
        }
        with open(index_path, "w") as f:
            json.dump(data, f, indent=2)

    def load_index(self) -> int:
        """Load the registry index from the lab folder. Returns count loaded."""
        index_path = self._lab_folder / self.INDEX_FILE
        if not index_path.exists():
            return 0

        with open(index_path, "r") as f:
            data = json.load(f)

        loaded = 0
        for name, comp_data in data.get("components", {}).items():
            try:
                comp = ComponentMeta.from_dict(comp_data)
                self._components[name] = comp
                loaded += 1
            except Exception:
                continue
        return loaded

    def get_stats(self) -> Dict[str, Any]:
        """Get registry statistics."""
        categories = self.list_categories()
        sources = {}
        for comp in self._components.values():
            sources[comp.source] = sources.get(comp.source, 0) + 1

        return {
            "total_components": len(self._components),
            "categories": {cat.value: count for cat, count in categories.items()},
            "sources": sources,
            "lab_folder": str(self._lab_folder),
        }


# Global registry instance
_registry: Optional[ComponentRegistry] = None


def get_registry(lab_folder: Optional[Path] = None) -> ComponentRegistry:
    """Get or create the global component registry."""
    global _registry
    if _registry is None:
        _registry = ComponentRegistry(lab_folder)
    return _registry


def reset_registry() -> None:
    """Reset the global registry (useful for testing)."""
    global _registry
    _registry = None
