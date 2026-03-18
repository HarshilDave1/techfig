import os
import json
from typing import Any, Dict, List, Union
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from scipy.integrate import solve_ivp

try:
    from manim import (
        Scene, Rectangle, Circle, Text, Arrow, VGroup,
        config, FadeIn, Create
    )
except ImportError:
    # Allow importing engine for CLI help even if manim is missing
    Scene = object

from techfig.utils.data_loader import load_data

class DiagramScene(Scene):
    def __init__(self, spec: Dict[str, Any], **kwargs):
        self.spec = spec
        super().__init__(**kwargs)

    def construct(self):
        elements = self.spec.get("elements", [])
        connections = self.spec.get("connections", [])
        
        mobjects = {}
        
        for el in elements:
            el_type = el.get("type", "box")
            el_id = el.get("id", f"el_{len(mobjects)}")
            text = el.get("text", "")
            
            scale_factor = 0.05
            sc_x = float(el.get("x", 0)) * scale_factor - 7
            sc_y = -(float(el.get("y", 0)) * scale_factor - 4)
            
            fill_color = "BLUE"
            if el.get("color") == "accent":
                fill_color = "RED"
                
            mob = None
            if el_type == "box":
                w = float(el.get("w", 120)) * scale_factor
                h = float(el.get("h", 60)) * scale_factor
                mob = Rectangle(width=w, height=h, color=fill_color)
            elif el_type == "circle":
                r = float(el.get("r", 40)) * scale_factor
                mob = Circle(radius=r, color=fill_color)
            else:
                w = float(el.get("w", 100)) * scale_factor
                h = float(el.get("h", 100)) * scale_factor
                mob = Rectangle(width=w, height=h, color=fill_color)
                
            mob.move_to([sc_x, sc_y, 0])
            
            if text:
                t = Text(text, font_size=24)
                t.move_to(mob.get_center())
                mobjects[el_id] = VGroup(mob, t)
            else:
                mobjects[el_id] = mob

        self.play(*[FadeIn(mob) for mob in mobjects.values()], run_time=1.5)
        self.wait(0.5)

        arrows = []
        for conn in connections:
            source_id = conn.get("from")
            target_id = conn.get("to")
            if source_id in mobjects and target_id in mobjects:
                src = mobjects[source_id]
                dst = mobjects[target_id]
                
                src_point = src.get_boundary_point(dst.get_center() - src.get_center())
                dst_point = dst.get_boundary_point(src.get_center() - dst.get_center())
                
                arrow = Arrow(start=src_point, end=dst_point, buff=0.1)
                arrows.append(arrow)

        if arrows:
            self.play(*[Create(arr) for arr in arrows], run_time=1)
            self.wait(1)

def _create_manim_animation(spec: dict, output_path: str, quality: str = "l", preview: bool = False):
    try:
        import manim
    except ImportError:
        raise ImportError("Manim is not installed. Please install it using `pip install manim`.")

    if not output_path.endswith(".mp4"):
         output_path += ".mp4"
         
    config.media_dir = os.path.dirname(os.path.abspath(output_path)) or "."
    quality_map = {"l": "low", "m": "medium", "h": "high"}
    manim_quality = quality_map.get(quality, "medium")
    config.quality = f"{manim_quality}_quality"
    config.preview = preview
    config.output_file = os.path.basename(output_path)
    config.verbosity = "INFO" if preview else "WARNING"

    scene = DiagramScene(spec)
    scene.render()
    
    import shutil
    import glob
    videos_dir = os.path.join(config.media_dir, "videos", "1080p60")
    if quality == "l":
        videos_dir = os.path.join(config.media_dir, "videos", "480p15")
    elif quality == "m":
        videos_dir = os.path.join(config.media_dir, "videos", "720p30")
        
    search_pattern = os.path.join(config.media_dir, "videos", "**", "*.mp4")
    generated_files = glob.glob(search_pattern, recursive=True)
    
    if generated_files:
        latest_file = max(generated_files, key=os.path.getmtime)
        if os.path.abspath(latest_file) != os.path.abspath(output_path):
             shutil.move(latest_file, output_path)
             
    return output_path

def _deriv_double_pendulum(t, state, L1, L2, m1, m2, g):
    """Derivatives for a double pendulum."""
    dydx = np.zeros_like(state)
    theta1, z1, theta2, z2 = state
    
    delta = theta2 - theta1
    den1 = (m1 + m2) * L1 - m2 * L1 * np.cos(delta) * np.cos(delta)
    
    dydx[0] = z1
    dydx[1] = ((m2 * L1 * z1 * z1 * np.sin(delta) * np.cos(delta)
                + m2 * g * np.sin(theta2) * np.cos(delta)
                + m2 * L2 * z2 * z2 * np.sin(delta)
                - (m1 + m2) * g * np.sin(theta1)) / den1)
    
    dydx[2] = z2
    den2 = (L2 / L1) * den1
    dydx[3] = ((-m2 * L2 * z2 * z2 * np.sin(delta) * np.cos(delta)
                + (m1 + m2) * g * np.sin(theta1) * np.cos(delta)
                - (m1 + m2) * L1 * z1 * z1 * np.sin(delta)
                - (m1 + m2) * g * np.sin(theta2)) / den2)
    return dydx

def _deriv_three_body(t, state, G, m1, m2, m3):
    """Derivatives for the 3-body problem (planar)."""
    # state = [x1, y1, vx1, vy1, x2, y2, vx2, vy2, x3, y3, vx3, vy3]
    dydx = np.zeros_like(state)
    
    # Velocities
    dydx[0:2] = state[2:4]
    dydx[4:6] = state[6:8]
    dydx[8:10] = state[10:12]
    
    r1 = state[0:2]
    r2 = state[4:6]
    r3 = state[8:10]
    
    def accel(pos, other_mass, other_pos):
        vec = other_pos - pos
        dist = np.linalg.norm(vec) + 1e-5 # prevent division by zero
        return G * other_mass * vec / dist**3
        
    # Accelerations
    dydx[2:4] = accel(r1, m2, r2) + accel(r1, m3, r3)
    dydx[6:8] = accel(r2, m1, r1) + accel(r2, m3, r3)
    dydx[10:12] = accel(r3, m1, r1) + accel(r3, m2, r2)
    
    return dydx

def _create_physics_animation(spec: dict, output_path: str, fps: int = 30):
    system_type = spec.get("system", "double_pendulum")
    duration = float(spec.get("duration", 10.0))
    t_eval = np.linspace(0, duration, int(fps * duration))
    
    plt.style.use('dark_background' if spec.get("theme") == "dark" else 'default')
    fig, ax = plt.subplots(figsize=(6, 6))

    if system_type == "double_pendulum":
        # Params
        L1 = float(spec.get("L1", 1.0))
        L2 = float(spec.get("L2", 1.0))
        m1 = float(spec.get("m1", 1.0))
        m2 = float(spec.get("m2", 1.0))
        g = float(spec.get("g", 9.81))
        
        state0 = spec.get("initial_state", [np.pi/2, 0.0, np.pi/2, 0.0]) # [theta1, w1, theta2, w2]
        
        sol = solve_ivp(_deriv_double_pendulum, [0, duration], state0, 
                        args=(L1, L2, m1, m2, g), t_eval=t_eval, method='RK45')
        
        theta1, theta2 = sol.y[0], sol.y[2]
        
        # Coordinates
        x1 = L1 * np.sin(theta1)
        y1 = -L1 * np.cos(theta1)
        x2 = x1 + L2 * np.sin(theta2)
        y2 = y1 - L2 * np.cos(theta2)
        
        ax.set_xlim(-(L1+L2)*1.1, (L1+L2)*1.1)
        ax.set_ylim(-(L1+L2)*1.1, (L1+L2)*1.1)
        ax.set_aspect('equal')
        ax.grid(True, alpha=0.3)
        ax.set_title("Double Pendulum", fontsize=14)
        
        line, = ax.plot([], [], 'o-', lw=2, markersize=8, color='#FF5733')
        trace, = ax.plot([], [], '-', lw=1, color='#FFC300', alpha=0.5)
        
        trace_x, trace_y = [], []
        
        def init():
            line.set_data([], [])
            trace.set_data([], [])
            return line, trace
            
        def update(i):
            thisx = [0, x1[i], x2[i]]
            thisy = [0, y1[i], y2[i]]
            
            trace_x.append(x2[i])
            trace_y.append(y2[i])
            # Keep trail length reasonable
            if len(trace_x) > fps * 2:
                trace_x.pop(0)
                trace_y.pop(0)

            line.set_data(thisx, thisy)
            trace.set_data(trace_x, trace_y)
            return line, trace
            
        anim = animation.FuncAnimation(fig, update, frames=len(t_eval),
                                      init_func=init, blit=True, interval=1000/fps)
                                      
    elif system_type == "three_body":
        # Params
        G = float(spec.get("G", 1.0))
        m1, m2, m3 = float(spec.get("m1", 1.0)), float(spec.get("m2", 1.0)), float(spec.get("m3", 1.0))
        
        # Figure 8 initial conditions if none specified
        state0 = spec.get("initial_state", [
            0.97000436, -0.24308753, 0.4662036850, 0.4323657300,   # m1: x, y, vx, vy
            -0.97000436, 0.24308753, 0.4662036850, 0.4323657300,   # m2: x, y, vx, vy
            0.0, 0.0, -2*0.4662036850, -2*0.4323657300             # m3: x, y, vx, vy
        ])
        
        sol = solve_ivp(_deriv_three_body, [0, duration], state0, 
                        args=(G, m1, m2, m3), t_eval=t_eval, method='RK45', atol=1e-8, rtol=1e-8)
        
        r1, r2, r3 = sol.y[0:2], sol.y[4:6], sol.y[8:10]
        
        ax.set_aspect('equal')
        
        lim = float(spec.get("lim", 2.0))
        ax.set_xlim(-lim, lim)
        ax.set_ylim(-lim, lim)
        ax.grid(True, alpha=0.3)
        ax.set_title("Three-Body Problem", fontsize=14)
        
        lines = []
        colors = ['#FF5733', '#33FF57', '#3357FF']
        traces = []
        for i in range(3):
            line, = ax.plot([], [], 'o', markersize=8, color=colors[i])
            trace, = ax.plot([], [], '-', lw=1, color=colors[i], alpha=0.5)
            lines.append(line)
            traces.append((trace, [], [])) # trace line, x_list, y_list
            
        def init():
            for line, (trace, _, _) in zip(lines, traces):
                line.set_data([], [])
                trace.set_data([], [])
            return [l for l in lines] + [t[0] for t in traces]
            
        def update(i):
            pos = [r1[:, i], r2[:, i], r3[:, i]]
            for j, (line, trace_data) in enumerate(zip(lines, traces)):
                trace, tx, ty = trace_data
                tx.append(pos[j][0])
                ty.append(pos[j][1])
                if len(tx) > fps * 3:
                     tx.pop(0)
                     ty.pop(0)
                line.set_data([pos[j][0]], [pos[j][1]])
                trace.set_data(tx, ty)
            
            return [l for l in lines] + [t[0] for t in traces]
            
        anim = animation.FuncAnimation(fig, update, frames=len(t_eval),
                                      init_func=init, blit=True, interval=1000/fps)
    else:
        plt.close(fig)
        raise ValueError(f"Unknown physics system: {system_type}")

    plt.tight_layout()
    
    # Save animation
    if output_path.endswith('.html'):
        with open(output_path, 'w') as f:
            f.write(anim.to_jshtml())
    elif output_path.endswith('.gif'):
        anim.save(output_path, writer='pillow', fps=fps)
    elif output_path.endswith('.mp4'):
        # Attempt to save MP4, fallback to GIF if ffmpeg is missing
        try:
            anim.save(output_path, writer='ffmpeg', fps=fps)
        except Exception as e:
            print(f"Failed to render MP4 (missing ffmpeg?). Falling back to GIF. Error: {e}")
            output_path = output_path.replace('.mp4', '.gif')
            anim.save(output_path, writer='pillow', fps=fps)
    else:
        # Default to HTML
        output_path += ".html"
        with open(output_path, 'w') as f:
            f.write(anim.to_jshtml())
            
    plt.close(fig)
    return output_path

def create_animation(spec: Union[str, Dict[str, Any]], output_path: str, quality: str = "m", preview: bool = False):
    """
    Renders an animated version of a physics simulation or diagram using Matplotlib Animation or Manim.
    """
    if isinstance(spec, str):
        with open(spec, 'r') as f:
            spec = json.load(f)
        
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    
    fps = 30 if quality in ["l", "m"] else 60
    
    spec_type = spec.get("type", "manim_diagram")
    if spec_type == "physics":
        out = _create_physics_animation(spec, output_path, fps=fps)
    elif spec_type == "diagram":
        from techfig.engines.diagram_manim_bridge import render_diagram_animation
        out = render_diagram_animation(spec, output_path, quality=quality, preview=False)
    else:
        out = _create_manim_animation(spec, output_path, quality=quality, preview=preview)

    if preview:
        import subprocess
        preview_path = None
        if output_path.endswith(('.mp4', '.gif')):
            preview_path = output_path.rsplit('.', 1)[0] + '_preview.png'
            try:
                subprocess.run([
                    "ffmpeg", "-y", "-i", output_path, "-vframes", "1", "-f", "image2", preview_path
                ], check=True, capture_output=True)
            except Exception as e:
                print(f"Failed to generate preview: {e}")
                preview_path = None
                
        file_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
        return {
            "output_path": output_path,
            "preview_path": preview_path,
            "size_bytes": file_size,
            "type": spec_type
        }
        
    return out
