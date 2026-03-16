"""Lab Folder management for custom user components.

The Lab Folder is a user-writable directory (~/.techfig/components by default)
where scientists can place custom SVG/PNG files for use in diagrams.

Features:
- Auto-indexing of component files
- Metadata extraction from filenames and file contents
- Dynamic component saving (for LLM-generated components)
- Component search and retrieval
"""
from __future__ import annotations

import json
import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from xml.etree import ElementTree as ET

from techfig.components.registry import (
    ComponentRegistry,
    ComponentMeta,
    ComponentCategory,
    get_registry,
)


# Supported file extensions
SUPPORTED_EXTENSIONS = {".svg", ".png", ".jpg", ".jpeg", ".pdf"}

# Metadata file name for custom components
METADATA_FILE = ".metadata.json"


def get_svg_metadata(svg_path: Path) -> Dict[str, Any]:
    """Extract metadata from an SVG file.

    Parses the SVG to extract:
    - Viewbox dimensions
    - Title (if present)
    - Description (if present)
    - Root element ID
    """
    metadata = {
        "width": None,
        "height": None,
        "viewbox": None,
        "title": None,
        "description": None,
        "element_count": 0,
    }

    try:
        tree = ET.parse(svg_path)
        root = tree.getroot()

        # Remove namespace prefixes for easier parsing
        for elem in root.iter():
            if "}" in elem.tag:
                elem.tag = elem.tag.split("}")[1]

        # Get viewBox
        viewbox = root.get("viewBox")
        if viewbox:
            metadata["viewbox"] = viewbox
            parts = viewbox.split()
            if len(parts) == 4:
                metadata["width"] = float(parts[2])
                metadata["height"] = float(parts[3])

        # Get width/height attributes
        if root.get("width"):
            metadata["width"] = float(re.sub(r"[^0-9.]", "", root.get("width", "0")))
        if root.get("height"):
            metadata["height"] = float(re.sub(r"[^0-9.]", "", root.get("height", "0")))

        # Get title
        title_elem = root.find("title")
        if title_elem is not None and title_elem.text:
            metadata["title"] = title_elem.text

        # Get description
        desc_elem = root.find("desc")
        if desc_elem is not None and desc_elem.text:
            metadata["description"] = desc_elem.text

        # Count elements
        metadata["element_count"] = len(list(root.iter()))

    except Exception:
        pass

    return metadata


def infer_category_from_filename(filename: str) -> ComponentCategory:
    """Infer component category from filename patterns."""
    name_lower = filename.lower()

    # Circuit keywords
    circuit_keywords = ["resistor", "capacitor", "inductor", "diode", "transistor", 
                       "circuit", "opamp", "fet", "bjt", "led", "battery", "ground"]
    if any(kw in name_lower for kw in circuit_keywords):
        return ComponentCategory.CIRCUIT

    # Physics keywords
    physics_keywords = ["mirror", "lens", "prism", "laser", "beam", "optical",
                       "wave", "particle", "field", "force", "mass"]
    if any(kw in name_lower for kw in physics_keywords):
        return ComponentCategory.PHYSICS

    # Optics keywords
    optics_keywords = ["optic", "filter", "polarizer", "waveplate", "grating"]
    if any(kw in name_lower for kw in optics_keywords):
        return ComponentCategory.OPTICS

    # Mechanics keywords
    mechanics_keywords = ["gear", "spring", "lever", "pulley", "bearing", "motor"]
    if any(kw in name_lower for kw in mechanics_keywords):
        return ComponentCategory.MECHANICS

    # Chemistry keywords
    chemistry_keywords = ["flask", "beaker", "molecule", "atom", "bond", "reaction"]
    if any(kw in name_lower for kw in chemistry_keywords):
        return ComponentCategory.CHEMISTRY

    # Biology keywords
    biology_keywords = ["cell", "dna", "protein", "membrane", "organism", "gene"]
    if any(kw in name_lower for kw in biology_keywords):
        return ComponentCategory.BIOLOGY

    return ComponentCategory.CUSTOM


def infer_tags_from_filename(filename: str) -> List[str]:
    """Extract tags from filename (words separated by underscores/dashes)."""
    # Remove extension
    name = Path(filename).stem
    # Split on underscores, dashes, spaces
    words = re.split(r"[_\-\s]++", name)
    # Lowercase and filter short words
    tags = [w.lower() for w in words if len(w) > 2]
    return tags


def generate_component_name(filename: str, existing_names: List[str]) -> str:
    """Generate a unique component name from filename."""
    base_name = Path(filename).stem.lower()
    base_name = re.sub(r"[^a-z0-9_]", "_", base_name)
    base_name = re.sub(r"_+", "_", base_name).strip("_")

    if base_name not in existing_names:
        return base_name

    # Add suffix to make unique
    counter = 1
    while f"{base_name}_{counter}" in existing_names:
        counter += 1
    return f"{base_name}_{counter}"


class LabFolder:
    """Manages custom components in the user's lab folder.

    The lab folder is a directory where users can place custom SVG/PNG files
    that will be automatically indexed and available for use in diagrams.

    Example:
        lab = LabFolder()
        lab.index_components()  # Scan for new components

        # Save a generated component
        lab.save_component("my_laser", svg_content, 
                          category="optics", tags=["laser", "photonics"])
    """

    def __init__(self, folder_path: Optional[Path] = None):
        self.folder = folder_path or (Path.home() / ".techfig" / "components")
        self.folder.mkdir(parents=True, exist_ok=True)
        self._metadata: Dict[str, Dict[str, Any]] = {}
        self._load_metadata()

    def _metadata_path(self) -> Path:
        return self.folder / METADATA_FILE

    def _load_metadata(self) -> None:
        """Load stored component metadata."""
        meta_path = self._metadata_path()
        if meta_path.exists():
            try:
                with open(meta_path, "r") as f:
                    self._metadata = json.load(f)
            except Exception:
                self._metadata = {}

    def _save_metadata(self) -> None:
        """Persist component metadata."""
        meta_path = self._metadata_path()
        with open(meta_path, "w") as f:
            json.dump(self._metadata, f, indent=2)

    def index_components(self, registry: Optional[ComponentRegistry] = None) -> int:
        """Scan the folder and index all components.

        Args:
            registry: Registry to register components with. Uses global if None.

        Returns:
            Number of new components indexed.
        """
        if registry is None:
            registry = get_registry()

        indexed = 0
        existing_names = [c.name for c in registry.list_all(ComponentCategory.CUSTOM)]

        for ext in SUPPORTED_EXTENSIONS:
            for file_path in self.folder.glob(f"*{ext}"):
                # Skip metadata file
                if file_path.name.startswith("."):
                    continue

                # Get or create component name
                component_name = self._metadata.get(file_path.name, {}).get("name")
                if not component_name:
                    component_name = generate_component_name(
                        file_path.name, existing_names
                    )
                    existing_names.append(component_name)

                # Get or infer category
                category_str = self._metadata.get(file_path.name, {}).get("category")
                if category_str:
                    try:
                        category = ComponentCategory(category_str)
                    except ValueError:
                        category = infer_category_from_filename(file_path.name)
                else:
                    category = infer_category_from_filename(file_path.name)

                # Get or infer tags
                tags = self._metadata.get(file_path.name, {}).get("tags", [])
                if not tags:
                    tags = infer_tags_from_filename(file_path.name)

                # Get description
                description = self._metadata.get(file_path.name, {}).get("description", "")
                if not description:
                    description = f"Custom component: {component_name}"

                # Create and register component
                meta = ComponentMeta(
                    name=component_name,
                    category=category,
                    source="lab_folder",
                    tags=tags,
                    description=description,
                    file_path=str(file_path),
                    created_at=datetime.now().isoformat(),
                )
                registry.register(meta)
                indexed += 1

                # Update local metadata
                self._metadata[file_path.name] = {
                    "name": component_name,
                    "category": category.value,
                    "tags": tags,
                    "description": description,
                }

        self._save_metadata()
        return indexed

    def save_component(
        self,
        name: str,
        content: str,  # SVG content or base64 for images
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        description: str = "",
        file_format: str = "svg",
        registry: Optional[ComponentRegistry] = None,
    ) -> Path:
        """Save a new custom component.

        Args:
            name: Component name (will be used as filename)
            content: SVG content string
            category: Category string (circuit, physics, optics, etc.)
            tags: List of tags for search
            description: Human-readable description
            file_format: File format (svg, png)
            registry: Registry to register with

        Returns:
            Path to saved component file.
        """
        if registry is None:
            registry = get_registry()

        # Sanitize name for filename
        safe_name = re.sub(r"[^a-z0-9_]", "_", name.lower())
        filename = f"{safe_name}.{file_format}"
        file_path = self.folder / filename

        # Handle duplicates
        counter = 1
        while file_path.exists():
            filename = f"{safe_name}_{counter}.{file_format}"
            file_path = self.folder / filename
            counter += 1

        # Save file
        if file_format == "svg":
            with open(file_path, "w") as f:
                f.write(content)
        else:
            # Assume content is base64 for non-svg formats
            import base64
            with open(file_path, "wb") as f:
                f.write(base64.b64decode(content))

        # Determine category
        try:
            cat = ComponentCategory(category.lower()) if category else ComponentCategory.CUSTOM
        except ValueError:
            cat = ComponentCategory.CUSTOM

        # Create metadata
        meta = ComponentMeta(
            name=name.lower(),
            category=cat,
            source="lab_folder",
            tags=tags or [name.lower()],
            description=description or f"Custom component: {name}",
            file_path=str(file_path),
            created_at=datetime.now().isoformat(),
        )
        registry.register(meta)

        # Update local metadata
        self._metadata[filename] = {
            "name": name.lower(),
            "category": cat.value,
            "tags": tags or [name.lower()],
            "description": description or f"Custom component: {name}",
        }
        self._save_metadata()

        return file_path

    def delete_component(self, name: str, registry: Optional[ComponentRegistry] = None) -> bool:
        """Delete a custom component by name.

        Returns True if deleted, False if not found.
        """
        if registry is None:
            registry = get_registry()

        meta = registry.get(name)
        if meta is None or meta.source != "lab_folder":
            return False

        if meta.file_path:
            file_path = Path(meta.file_path)
            if file_path.exists():
                file_path.unlink()

            # Remove from metadata
            self._metadata.pop(file_path.name, None)
            self._save_metadata()

        registry.unregister(name)
        return True

    def get_component_path(self, name: str) -> Optional[Path]:
        """Get the file path for a component by name."""
        registry = get_registry()
        meta = registry.get(name)
        if meta and meta.file_path:
            return Path(meta.file_path)
        return None

    def list_components(self) -> List[Dict[str, Any]]:
        """List all custom components in the lab folder."""
        components = []
        for ext in SUPPORTED_EXTENSIONS:
            for file_path in self.folder.glob(f"*{ext}"):
                if file_path.name.startswith("."):
                    continue
                meta = self._metadata.get(file_path.name, {})
                components.append({
                    "filename": file_path.name,
                    "path": str(file_path),
                    "name": meta.get("name", file_path.stem),
                    "category": meta.get("category", "custom"),
                    "tags": meta.get("tags", []),
                    "description": meta.get("description", ""),
                })
        return components


def get_lab_folder(folder_path: Optional[Path] = None) -> LabFolder:
    """Get or create a LabFolder instance."""
    return LabFolder(folder_path)
