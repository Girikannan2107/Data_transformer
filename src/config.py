import json
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class PipelineConfig:
    def __init__(self, config_path: str):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                self._raw_config = json.load(f)
        except Exception as e:
            logger.error(f"Robustness Guard: Failed to load config {config_path}. {e}")
            raise ValueError(f"Invalid or missing configuration: {e}")

        # Extract settings with defaults
        self.fields = self._raw_config.get("fields", [])
        self.include_confidence = self._raw_config.get("include_confidence", True)
        self.include_provenance = self._raw_config.get("include_provenance", True)
        
        # Policy for missing data: "null", "omit", or "error"
        self.on_missing = self._raw_config.get("on_missing", "null")