import os
from techfig.engines.animations import create_animation

def main():
    output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")
    os.makedirs(output_dir, exist_ok=True)
    
    # 1. Double Pendulum Simulation
    pendulum_spec = {
        "type": "physics",
        "system": "double_pendulum",
        "duration": 5.0,  # 5 seconds
        "theme": "dark",
        "L1": 1.0, "L2": 1.0,
        "m1": 1.0, "m2": 1.0,
        "initial_state": [1.57, 0.0, 1.57, 0.0] # horizontal start
    }
    
    pendulum_out = os.path.join(output_dir, "double_pendulum.gif")
    print(f"Generating Double Pendulum animation -> {pendulum_out}")
    create_animation(pendulum_spec, pendulum_out, quality="m")
    
    # 2. Three-Body Problem Simulation (Figure-8 orbit)
    three_body_spec = {
        "type": "physics",
        "system": "three_body",
        "duration": 5.0,
        "theme": "dark",
        "initial_state": [
            0.97000436, -0.24308753, 0.4662036850, 0.4323657300,   # m1
            -0.97000436, 0.24308753, 0.4662036850, 0.4323657300,   # m2
            0.0, 0.0, -2*0.4662036850, -2*0.4323657300             # m3
        ]
    }
    
    three_body_out = os.path.join(output_dir, "three_body.gif")
    print(f"Generating Three-Body Problem animation -> {three_body_out}")
    create_animation(three_body_spec, three_body_out, quality="m")

    print("\n✅ Done! Check the output/ folder for .gif animations.")

if __name__ == "__main__":
    main()
