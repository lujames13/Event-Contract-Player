import yaml
from pathlib import Path
from typing import Any

def load_constants() -> dict[str, Any]:
    """
    Load project constants from config/project_constants.yaml
    """
    # Assuming the project root is 3 levels up from this file
    config_path = Path(__file__).parents[3] / "config" / "project_constants.yaml"
    
    if not config_path.exists():
        # Fallback for different execution contexts
        config_path = Path("config/project_constants.yaml")
        
    if not config_path.exists():
        raise FileNotFoundError(f"Could not find config/project_constants.yaml at {config_path.absolute()}")
        
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
