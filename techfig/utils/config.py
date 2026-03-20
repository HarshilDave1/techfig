import yaml
from pathlib import Path

CONFIG_DIR = Path.home() / ".techfig"
CONFIG_PATH = CONFIG_DIR / "config.yaml"

DEFAULT_CONFIG = {
    "style": "nature",
    "pretty_model": "openai/dall-e-3",
    "dpi": 300,
    "quality": "l",
    "max_rounds": 5,
    "sketch_model": "gemini/gemini-2.5-pro",
}

def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_PATH, "r") as f:
            cfg = yaml.safe_load(f)
            return {**DEFAULT_CONFIG, **(cfg or {})}
    except Exception:
        return DEFAULT_CONFIG.copy()

def save_config(config_dict: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        yaml.safe_dump(config_dict, f, default_flow_style=False)

def get_config_val(key: str, default=None):
    return load_config().get(key, default)

def set_config_val(key: str, value: str):
    cfg = load_config()
    # Try casting numerical or booleans
    if value.lower() in ["true", "false"]:
        cfg[key] = value.lower() == "true"
    elif value.isdigit():
        cfg[key] = int(value)
    else:
        cfg[key] = value
    save_config(cfg)
