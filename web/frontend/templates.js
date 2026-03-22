/**
 * TechFig Demo — Built-in Templates
 *
 * Each template has a name, description, and a full diagram spec
 * that can be sent directly to the /api/reconstruct endpoint.
 */

const TEMPLATES = {
    optical_bench: {
        name: "Optical Bench",
        description: "Ti:Sapphire laser → mirror → lens → sample → CCD detector",
        category: "Physics",
        spec: {
            canvas: { width: 1000, height: 400 },
            elements: [
                { type: "box", id: "laser", x: -400, y: 0, w: 100, h: 50, text: "Ti:Sapphire\nLaser", color: "#c0392b", fill_opacity: 0.2 },
                { type: "box", id: "mirror1", x: -200, y: 0, w: 10, h: 60, rotation: -45, text: "M1", color: "#bdc3c7", fill_opacity: 0.8 },
                { type: "ellipse", id: "lens", x: 0, y: -200, rx: 10, ry: 40, text: "L1", color: "#3498db", fill_opacity: 0.3 },
                { type: "box", id: "sample", x: 200, y: -200, w: 40, h: 40, text: "Sample", color: "#8e44ad", fill_opacity: 0.5 },
                { type: "box", id: "detector", x: 400, y: -200, w: 60, h: 80, text: "CCD\nDetector", color: "#16a085", fill_opacity: 0.4 }
            ],
            connections: [
                { from: "laser", to: "mirror1", style: "arrow", color: "#ff0000", label: "Beam" },
                { from: "mirror1", to: "lens", style: "arrow", color: "#ff0000", route: "orthogonal" },
                { from: "lens", to: "sample", style: "arrow", color: "#ff0000" },
                { from: "sample", to: "detector", style: "arrow", color: "#ff0000", stroke_dash: "5,3", label: "Fluorescence" }
            ]
        }
    },

    simple_flowchart: {
        name: "Simple Flowchart",
        description: "Start → Process → Decision → End",
        category: "General",
        spec: {
            canvas: { width: 800, height: 600 },
            elements: [
                { type: "circle", id: "start", x: 0, y: -200, r: 40, text: "Start", color: "#10b981", fill_opacity: 0.3 },
                { type: "box", id: "process", x: 0, y: -50, w: 140, h: 60, text: "Process\nData", color: "#3b82f6", fill_opacity: 0.2 },
                { type: "diamond", id: "decision", x: 0, y: 100, w: 120, h: 90, text: "Valid?", color: "#f59e0b", fill_opacity: 0.2 },
                { type: "box", id: "output", x: 200, y: 100, w: 100, h: 50, text: "Output", color: "#8b5cf6", fill_opacity: 0.2 },
                { type: "circle", id: "end", x: 200, y: 250, r: 35, text: "End", color: "#ef4444", fill_opacity: 0.3 }
            ],
            connections: [
                { from: "start", to: "process", style: "arrow" },
                { from: "process", to: "decision", style: "arrow" },
                { from: "decision", to: "output", style: "arrow", label: "Yes" },
                { from: "decision", to: "process", style: "arrow", label: "No", route: "orthogonal", stroke_dash: "5,3" },
                { from: "output", to: "end", style: "arrow" }
            ]
        }
    },

    cell_membrane: {
        name: "Cell Membrane",
        description: "Phospholipid bilayer with receptor, channel, and transport protein",
        category: "Biology",
        spec: {
            canvas: { width: 1200, height: 600 },
            elements: [
                { type: "box", id: "extracellular", x: 0, y: -250, w: 900, h: 40, text: "Extracellular Space", color: "#06b6d4", fill_opacity: 0.1 },
                { type: "box", id: "membrane_top", x: 0, y: -150, w: 900, h: 20, text: "", color: "#f59e0b", fill_opacity: 0.4 },
                { type: "box", id: "membrane_bot", x: 0, y: -100, w: 900, h: 20, text: "", color: "#f59e0b", fill_opacity: 0.4 },
                { type: "box", id: "intracellular", x: 0, y: 0, w: 900, h: 40, text: "Intracellular (Cytoplasm)", color: "#8b5cf6", fill_opacity: 0.1 },
                { type: "ellipse", id: "receptor", x: -250, y: -125, rx: 30, ry: 55, text: "Receptor", color: "#ef4444", fill_opacity: 0.4 },
                { type: "box", id: "channel", x: 0, y: -125, w: 30, h: 90, text: "Ion\nChannel", color: "#3b82f6", fill_opacity: 0.3 },
                { type: "ellipse", id: "pump", x: 250, y: -125, rx: 35, ry: 55, text: "Na+/K+\nPump", color: "#10b981", fill_opacity: 0.4 },
                { type: "circle", id: "ligand", x: -250, y: -230, r: 15, text: "L", color: "#ef4444", fill_opacity: 0.7 }
            ],
            connections: [
                { from: "ligand", to: "receptor", style: "arrow", label: "Binding", stroke_dash: "5,3" }
            ]
        }
    },

    neural_network: {
        name: "Neural Network",
        description: "Simple 3-layer network: Input → Hidden → Output",
        category: "CS / ML",
        spec: {
            canvas: { width: 800, height: 600 },
            elements: [
                { type: "text", x: -250, y: -270, text: "Input Layer", font_size: 14, color: "#64748b" },
                { type: "circle", id: "i1", x: -250, y: -200, r: 25, text: "x₁", color: "#3b82f6", fill_opacity: 0.2 },
                { type: "circle", id: "i2", x: -250, y: -80, r: 25, text: "x₂", color: "#3b82f6", fill_opacity: 0.2 },
                { type: "circle", id: "i3", x: -250, y: 40, r: 25, text: "x₃", color: "#3b82f6", fill_opacity: 0.2 },

                { type: "text", x: 0, y: -270, text: "Hidden Layer", font_size: 14, color: "#64748b" },
                { type: "circle", id: "h1", x: 0, y: -200, r: 25, text: "h₁", color: "#8b5cf6", fill_opacity: 0.2 },
                { type: "circle", id: "h2", x: 0, y: -80, r: 25, text: "h₂", color: "#8b5cf6", fill_opacity: 0.2 },
                { type: "circle", id: "h3", x: 0, y: 40, r: 25, text: "h₃", color: "#8b5cf6", fill_opacity: 0.2 },
                { type: "circle", id: "h4", x: 0, y: 160, r: 25, text: "h₄", color: "#8b5cf6", fill_opacity: 0.2 },

                { type: "text", x: 250, y: -270, text: "Output Layer", font_size: 14, color: "#64748b" },
                { type: "circle", id: "o1", x: 250, y: -140, r: 25, text: "ŷ₁", color: "#10b981", fill_opacity: 0.3 },
                { type: "circle", id: "o2", x: 250, y: 0, r: 25, text: "ŷ₂", color: "#10b981", fill_opacity: 0.3 }
            ],
            connections: [
                { from: "i1", to: "h1", style: "line", color: "#475569" },
                { from: "i1", to: "h2", style: "line", color: "#475569" },
                { from: "i1", to: "h3", style: "line", color: "#475569" },
                { from: "i1", to: "h4", style: "line", color: "#475569" },
                { from: "i2", to: "h1", style: "line", color: "#475569" },
                { from: "i2", to: "h2", style: "line", color: "#475569" },
                { from: "i2", to: "h3", style: "line", color: "#475569" },
                { from: "i2", to: "h4", style: "line", color: "#475569" },
                { from: "i3", to: "h1", style: "line", color: "#475569" },
                { from: "i3", to: "h2", style: "line", color: "#475569" },
                { from: "i3", to: "h3", style: "line", color: "#475569" },
                { from: "i3", to: "h4", style: "line", color: "#475569" },
                { from: "h1", to: "o1", style: "arrow", color: "#475569" },
                { from: "h1", to: "o2", style: "arrow", color: "#475569" },
                { from: "h2", to: "o1", style: "arrow", color: "#475569" },
                { from: "h2", to: "o2", style: "arrow", color: "#475569" },
                { from: "h3", to: "o1", style: "arrow", color: "#475569" },
                { from: "h3", to: "o2", style: "arrow", color: "#475569" },
                { from: "h4", to: "o1", style: "arrow", color: "#475569" },
                { from: "h4", to: "o2", style: "arrow", color: "#475569" }
            ]
        }
    },

    pcr_workflow: {
        name: "PCR Workflow",
        description: "Denaturation → Annealing → Extension cycle",
        category: "Biology",
        spec: {
            canvas: { width: 1000, height: 400 },
            elements: [
                { type: "box", id: "denature", x: -300, y: 0, w: 140, h: 70, text: "Denature\n95°C", color: "#ef4444", fill_opacity: 0.3 },
                { type: "box", id: "anneal", x: 0, y: 0, w: 140, h: 70, text: "Anneal\n55°C", color: "#3b82f6", fill_opacity: 0.3 },
                { type: "box", id: "extend", x: 300, y: 0, w: 140, h: 70, text: "Extend\n72°C", color: "#10b981", fill_opacity: 0.3 },
                { type: "text", x: 0, y: -120, text: "PCR Thermocycling (25-35 cycles)", font_size: 16, color: "#f59e0b" },
                { type: "text", x: -300, y: 80, text: "dsDNA → ssDNA", font_size: 11, color: "#94a3b8" },
                { type: "text", x: 0, y: 80, text: "Primers bind", font_size: 11, color: "#94a3b8" },
                { type: "text", x: 300, y: 80, text: "Taq polymerase", font_size: 11, color: "#94a3b8" }
            ],
            connections: [
                { from: "denature", to: "anneal", style: "arrow", label: "Cool" },
                { from: "anneal", to: "extend", style: "arrow", label: "Heat" },
                { from: "extend", to: "denature", style: "arrow", label: "Repeat", route: "orthogonal", stroke_dash: "5,3", color: "#f59e0b" }
            ]
        }
    }
};

// Make available globally
window.TEMPLATES = TEMPLATES;
