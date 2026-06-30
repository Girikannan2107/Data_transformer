import logging
from typing import Dict, Any, List
from src.models import InternalCandidateProfile, TrackedField
from src.config import PipelineConfig

logger = logging.getLogger(__name__)

class ProjectionEngine:
    def __init__(self, config: PipelineConfig):
        self.config = config

    def _extract_value(self, internal_dict: dict, from_path: str) -> Any:
        """
        Dynamically extracts a value from the internal dictionary using dot or bracket notation.
        e.g., 'emails[0]' extracts the first item from the emails array.
        """
        try:
            if "[" in from_path and from_path.endswith("]"):
                # Handle array indexing (e.g., "emails[0]")
                base_key, index_str = from_path[:-1].split("[")
                index = int(index_str)
                array_val = internal_dict.get(base_key, [])
                return array_val[index] if len(array_val) > index else None
            else:
                # Handle standard scalar keys
                return internal_dict.get(from_path)
        except Exception as e:
            logger.warning(f"Failed to extract path {from_path}: {e}")
            return None

    def _format_field(self, field_data: Any) -> Any:
        """
        Recursively strips out Provenance and Confidence wrappers if the config dictates it.
        """
        if field_data is None:
            return None

        # Handle a single TrackedField
        if isinstance(field_data, dict) and "value" in field_data and "provenance" in field_data:
            formatted = {"value": field_data["value"]}
            
            if self.config.include_confidence:
                formatted["confidence"] = field_data["provenance"].get("confidence")
            if self.config.include_provenance:
                formatted["provenance"] = field_data["provenance"]
                
            # If both are hidden, just return the raw value itself
            if not self.config.include_confidence and not self.config.include_provenance:
                return field_data["value"]
                
            return formatted

        # Handle arrays of TrackedFields (like skills)
        if isinstance(field_data, list):
            return [self._format_field(item) for item in field_data]

        return field_data

    def project(self, profile: InternalCandidateProfile) -> Dict[str, Any]:
        """
        Transforms the internal profile into the final output schema based on config.
        """
        # Convert Pydantic model to a standard dict for dynamic traversal
        internal_dict = profile.model_dump()
        projected_output = {}

        for field_def in self.config.fields:
            out_key = field_def["path"]
            # If "from" isn't specified, assume the internal key matches the output key
            internal_key = field_def.get("from", out_key)
            is_required = field_def.get("required", False)

            # 1. Extract the raw wrapped value
            raw_val = self._extract_value(internal_dict, internal_key)

            # 2. Handle Missing Values
            if raw_val is None or (isinstance(raw_val, list) and len(raw_val) == 0):
                if is_required and self.config.on_missing == "error":
                    raise ValueError(f"Validation Error: Required field '{out_key}' is missing.")
                elif self.config.on_missing == "omit":
                    continue
                else: # Default is "null"
                    projected_output[out_key] = None
                continue

            # 3. Format based on Provenance/Confidence toggles
            projected_output[out_key] = self._format_field(raw_val)

        # Inject overall confidence if requested (this isn't a TrackedField, just a float)
        if self.config.include_confidence:
            projected_output["overall_confidence"] = internal_dict.get("overall_confidence", 0.0)

        return projected_output