"""Data loading utilities for the figure engine.

Supports loading data from CSV, JSON, and Excel files, or parsing inline lists/dicts.
"""
import json
import pandas as pd
from typing import Union, Dict, Any, List
from pathlib import Path

# Type alias for data that matplotlib/seaborn can consume directly
PlotData = Union[pd.DataFrame, Dict[str, List[Any]], List[List[Any]]]

def load_data(data_source: Union[str, Path, PlotData]) -> pd.DataFrame:
    """Load data from a file path or return it if it's already a dataframe/dict.
    
    Args:
        data_source: A file path (str/Path) to a CSV/JSON/Excel file, 
                        or a raw dict/list of data.
                        
    Returns:
        A pandas DataFrame ready for plotting.
    """
    # If it's already a DataFrame, return it
    if isinstance(data_source, pd.DataFrame):
        return data_source
        
    # If it's a dict or list, convert to DataFrame
    if isinstance(data_source, (dict, list)):
        return pd.DataFrame(data_source)
        
    # Otherwise, treat it as a path
    path = Path(data_source)
    if not path.exists():
        raise FileNotFoundError(f"Data file not found: {path}")
        
    suffix = path.suffix.lower()
    
    if suffix == '.csv':
        return pd.read_csv(path)
    elif suffix in ['.xlsx', '.xls']:
        return pd.read_excel(path)
    elif suffix == '.json':
        # Simple JSON loading - assumes tabular structure
        with open(path, 'r') as f:
            data = json.load(f)
        return pd.DataFrame(data)
    else:
        raise ValueError(f"Unsupported data format: {suffix}. Use CSV, Excel, or JSON.")
