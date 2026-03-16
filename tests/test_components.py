"""Tests for the component library module."""
import pytest
import tempfile
from pathlib import Path

from techfig.components.registry import (
    ComponentRegistry,
    ComponentMeta,
    ComponentCategory,
    reset_registry,
)
from techfig.components.standard import (
    load_standard_components,
    list_available_components,
    is_schemdraw_available,
)
from techfig.components.lab_folder import (
    LabFolder,
    infer_category_from_filename,
    infer_tags_from_filename,
)


class TestComponentMeta:
    """Tests for ComponentMeta dataclass."""
    
    def test_create_component_meta(self):
        """Test creating component metadata."""
        meta = ComponentMeta(
            name="resistor",
            category=ComponentCategory.CIRCUIT,
            source="standard",
            tags=["R", "electrical"],
            description="Electrical resistor component",
        )
        assert meta.name == "resistor"
        assert meta.category == ComponentCategory.CIRCUIT
        assert meta.source == "standard"
        assert "R" in meta.tags
    
    def test_meta_to_dict(self):
        """Test serializing component metadata to dict."""
        meta = ComponentMeta(
            name="capacitor",
            category=ComponentCategory.CIRCUIT,
            source="standard",
        )
        data = meta.to_dict()
        assert data["name"] == "capacitor"
        assert data["category"] == "circuit"
        assert data["source"] == "standard"
    
    def test_meta_from_dict(self):
        """Test deserializing component metadata from dict."""
        data = {
            "name": "my_laser",
            "category": "optics",
            "source": "lab_folder",
            "tags": ["laser", "photonics"],
            "description": "Custom laser component",
        }
        meta = ComponentMeta.from_dict(data)
        assert meta.name == "my_laser"
        assert meta.category == ComponentCategory.OPTICS
        assert "laser" in meta.tags


class TestComponentRegistry:
    """Tests for ComponentRegistry."""
    
    def test_register_and_get_component(self):
        """Test registering and retrieving a component."""
        registry = ComponentRegistry()
        meta = ComponentMeta(
            name="test_resistor",
            category=ComponentCategory.CIRCUIT,
            source="standard",
        )
        registry.register(meta)
        
        retrieved = registry.get("test_resistor")
        assert retrieved is not None
        assert retrieved.name == "test_resistor"
    
    def test_get_nonexistent_component(self):
        """Test getting a component that doesn't exist."""
        registry = ComponentRegistry()
        assert registry.get("nonexistent") is None
    
    def test_unregister_component(self):
        """Test unregistering a component."""
        registry = ComponentRegistry()
        meta = ComponentMeta(
            name="to_remove",
            category=ComponentCategory.CIRCUIT,
            source="standard",
        )
        registry.register(meta)
        assert registry.get("to_remove") is not None
        
        result = registry.unregister("to_remove")
        assert result is True
        assert registry.get("to_remove") is None
    
    def test_search_by_name(self):
        """Test searching components by name."""
        registry = ComponentRegistry()
        registry.register(ComponentMeta(
            name="resistor", category=ComponentCategory.CIRCUIT, source="standard"
        ))
        registry.register(ComponentMeta(
            name="capacitor", category=ComponentCategory.CIRCUIT, source="standard"
        ))
        registry.register(ComponentMeta(
            name="inductor", category=ComponentCategory.CIRCUIT, source="standard"
        ))
        
        results = registry.search("res")
        assert len(results) == 1
        assert results[0].name == "resistor"
    
    def test_search_by_tag(self):
        """Test searching components by tag."""
        registry = ComponentRegistry()
        registry.register(ComponentMeta(
            name="resistor",
            category=ComponentCategory.CIRCUIT,
            source="standard",
            tags=["R", "resistance", "passive"],
        ))
        
        results = registry.search("passive")
        assert len(results) == 1
        assert results[0].name == "resistor"
    
    def test_filter_by_category(self):
        """Test listing components filtered by category."""
        registry = ComponentRegistry()
        registry.register(ComponentMeta(
            name="resistor", category=ComponentCategory.CIRCUIT, source="standard"
        ))
        registry.register(ComponentMeta(
            name="lens", category=ComponentCategory.OPTICS, source="standard"
        ))
        
        circuits = registry.list_all(category=ComponentCategory.CIRCUIT)
        assert len(circuits) == 1
        assert circuits[0].name == "resistor"
    
    def test_registry_stats(self):
        """Test getting registry statistics."""
        registry = ComponentRegistry()
        registry.register(ComponentMeta(
            name="resistor", category=ComponentCategory.CIRCUIT, source="standard"
        ))
        registry.register(ComponentMeta(
            name="custom", category=ComponentCategory.CUSTOM, source="lab_folder"
        ))
        
        stats = registry.get_stats()
        assert stats["total_components"] == 2
        assert "circuit" in stats["categories"]
        assert "custom" in stats["categories"]


class TestStandardComponents:
    """Tests for standard component library (schemdraw integration)."""
    
    def test_schemdraw_available(self):
        """Test that schemdraw is available."""
        assert is_schemdraw_available() is True
    
    def test_list_available_components(self):
        """Test listing available standard components."""
        components = list_available_components()
        assert len(components) > 0
        assert "resistor" in components
        assert "capacitor" in components
        assert "diode" in components
    
    def test_load_standard_components(self):
        """Test loading standard components into registry."""
        reset_registry()
        from techfig.components import get_registry
        registry = get_registry()
        
        loaded = load_standard_components(registry)
        assert loaded > 0
        
        # Check some common components are loaded
        assert registry.get("resistor") is not None
        assert registry.get("capacitor") is not None
        assert registry.get("battery") is not None
        
        reset_registry()
    
    @pytest.mark.skipif(not is_schemdraw_available(), reason="schemdraw not installed")
    def test_render_schemdraw_component(self):
        """Test rendering a schemdraw component to SVG."""
        from techfig.components import render_schemdraw_component
        
        reset_registry()
        from techfig.components import get_registry
        load_standard_components(get_registry())
        
        svg = render_schemdraw_component("resistor")
        assert svg is not None
        assert "<svg" in svg or "<svg" in svg
        
        reset_registry()


class TestLabFolder:
    """Tests for Lab Folder custom component management."""
    
    def test_infer_category_from_filename(self):
        """Test inferring category from filename."""
        assert infer_category_from_filename("resistor.svg") == ComponentCategory.CIRCUIT
        assert infer_category_from_filename("capacitor_custom.png") == ComponentCategory.CIRCUIT
        assert infer_category_from_filename("lens_biconvex.svg") == ComponentCategory.PHYSICS
        assert infer_category_from_filename("laser_photonics.svg") == ComponentCategory.PHYSICS
        assert infer_category_from_filename("gear_32t.svg") == ComponentCategory.MECHANICS
        assert infer_category_from_filename("cell_membrane.svg") == ComponentCategory.BIOLOGY
        assert infer_category_from_filename("beaker_100ml.svg") == ComponentCategory.CHEMISTRY
        assert infer_category_from_filename("random_thing.svg") == ComponentCategory.CUSTOM
    
    def test_infer_tags_from_filename(self):
        """Test extracting tags from filename."""
        tags = infer_tags_from_filename("laser_diode_red.svg")
        assert "laser" in tags
        assert "diode" in tags
        assert "red" in tags
        
        tags = infer_tags_from_filename("resistor-10k-ohm.png")
        assert "resistor" in tags
        assert "10k" in tags
        assert "ohm" in tags
    
    def test_lab_folder_creation(self):
        """Test lab folder creation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lab = LabFolder(Path(tmpdir))
            assert lab.folder.exists()
    
    def test_save_and_index_component(self):
        """Test saving and indexing a custom component."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lab = LabFolder(Path(tmpdir))
            reset_registry()
            from techfig.components import get_registry
            registry = get_registry()
            
            # Save a simple SVG
            svg_content = '''<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
                <circle cx="50" cy="50" r="40" fill="blue"/>
            </svg>'''
            
            path = lab.save_component(
                name="my_custom_laser",
                content=svg_content,
                category="optics",
                tags=["laser", "custom"],
                description="A custom laser component",
                registry=registry,
            )
            
            assert path.exists()
            assert path.suffix == ".svg"
            
            # Verify it's registered
            meta = registry.get("my_custom_laser")
            assert meta is not None
            assert meta.category == ComponentCategory.OPTICS
            assert "laser" in meta.tags
            
            reset_registry()
    
    def test_delete_component(self):
        """Test deleting a custom component."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lab = LabFolder(Path(tmpdir))
            reset_registry()
            from techfig.components import get_registry
            registry = get_registry()
            
            # Save a component
            svg_content = "<svg><circle r='10'/></svg>"
            path = lab.save_component(
                name="to_delete",
                content=svg_content,
                registry=registry,
            )
            
            assert path.exists()
            assert registry.get("to_delete") is not None
            
            # Delete it
            result = lab.delete_component("to_delete", registry)
            assert result is True
            assert not path.exists()
            assert registry.get("to_delete") is None
            
            reset_registry()
    
    def test_list_components(self):
        """Test listing components in lab folder."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lab = LabFolder(Path(tmpdir))
            reset_registry()
            from techfig.components import get_registry
            registry = get_registry()
            
            # Save a couple components
            lab.save_component("comp1", "<svg><rect/></svg>", registry=registry)
            lab.save_component("comp2", "<svg><circle/></svg>", registry=registry)
            
            components = lab.list_components()
            assert len(components) == 2
            
            reset_registry()


class TestIntegration:
    """Integration tests for the component system."""
    
    def test_full_workflow(self):
        """Test the full component workflow: load standard + custom + search."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reset_registry()
            from techfig.components import get_registry
            registry = get_registry()
            
            # Load standard components
            standard_count = load_standard_components(registry)
            assert standard_count >= 30  # Should have 40+ components
            
            # Create lab folder and save custom component
            lab = LabFolder(Path(tmpdir))
            lab.save_component(
                name="my_laser",
                content="<svg><circle cx='50' cy='50' r='25'/></svg>",
                category="optics",
                tags=["laser", "photonics"],
                registry=registry,
            )
            
            # Search across all components
            laser_results = registry.search("laser")
            assert len(laser_results) >= 1
            
            # Get stats
            stats = registry.get_stats()
            assert stats["total_components"] > 30
            assert "standard" in stats["sources"]
            assert "lab_folder" in stats["sources"]
            
            reset_registry()
