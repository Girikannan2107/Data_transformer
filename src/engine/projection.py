# src/engine/projection.py
import logging
from typing import Dict, Any, List
from src.models import InternalCandidateProfile
from src.config import PipelineConfig

logger = logging.getLogger(__name__)

class ProjectionEngine:
    """
    Projection Engine.
    Transforms the internal canonical candidate profile into output formats
    based on the output schema runtime config. Supports nested paths, computed fields,
    and metadata toggles (confidence/provenance).
    """
    def __init__(self, config: PipelineConfig):
        self.config = config

    def _extract_value(self, internal_dict: dict, from_path: str) -> Any:
        """
        Dynamically extracts a value from the dictionary using dot notation or array brackets.
        e.g., 'emails[0]', 'location.city', 'links.github'
        """
        try:
            parts = from_path.split('.')
            current = internal_dict
            
            for part in parts:
                if current is None:
                    return None
                    
                # If current represents a TrackedField, automatically step into its value
                if isinstance(current, dict) and "value" in current and "provenance" in current:
                    current = current["value"]
                    
                if current is None:
                    return None
                    
                # Handle bracket notation, e.g. "emails[0]"
                if "[" in part and part.endswith("]"):
                    base_key, index_str = part[:-1].split("[")
                    index = int(index_str)
                    if isinstance(current, dict):
                        array_val = current.get(base_key, [])
                    else:
                        array_val = getattr(current, base_key, [])
                    current = array_val[index] if len(array_val) > index else None
                else:
                    if isinstance(current, dict):
                        current = current.get(part)
                    else:
                        current = getattr(current, part, None)
                        
            return current
        except Exception as e:
            logger.warning(f"Failed to extract path {from_path}: {e}")
            return None

    def _format_field_by_type(self, field_data: Any, out_key: str) -> Any:
        if field_data is None:
            return None

        # 1. Custom formatting for skills: name, confidence, sources
        if out_key == "skills" and isinstance(field_data, list):
            formatted_skills = []
            for item in field_data:
                if isinstance(item, dict) and "value" in item and "provenance" in item:
                    prov = item["provenance"]
                    formatted_skills.append({
                        "name": item["value"],
                        "confidence": float(prov.get("confidence", 0.0)),
                        "sources": prov.get("supporting_sources", [prov.get("source")])
                    })
            return formatted_skills

        # 2. Custom formatting for emails/phones: value, confidence
        if out_key in ["emails", "phones"] and isinstance(field_data, list):
            formatted_list = []
            for item in field_data:
                if isinstance(item, dict) and "value" in item and "provenance" in item:
                    formatted_list.append({
                        "value": item["value"],
                        "confidence": float(item["provenance"].get("confidence", 0.0))
                    })
            return formatted_list

        # 3. Strip TrackedField wrappers completely for complex objects and list items
        if out_key in ["experience", "education"] and isinstance(field_data, list):
            return [item["value"] for item in field_data if isinstance(item, dict) and "value" in item]

        if out_key in ["location", "links"] and isinstance(field_data, dict) and "value" in field_data:
            return field_data["value"]

        # 4. Standard scalar fields (headline, years_experience)
        if out_key in ["headline", "years_experience"] and isinstance(field_data, dict) and "value" in field_data:
            return field_data["value"]

        # Fallback to standard formatter
        return self._format_field(field_data)

    def _format_field(self, field_data: Any) -> Any:
        """
        Recursively strips out Provenance and Confidence wrappers based on configuration.
        """
        if field_data is None:
            return None

        # Handle single TrackedField
        if isinstance(field_data, dict) and "value" in field_data and "provenance" in field_data:
            formatted = {"value": field_data["value"]}
            
            if self.config.include_confidence:
                formatted["confidence"] = field_data["provenance"].get("confidence")
            if self.config.include_provenance:
                # Include provenance details
                formatted["provenance"] = field_data["provenance"]
                
            # If both options are false, return the raw un-wrapped value
            if not self.config.include_confidence and not self.config.include_provenance:
                return field_data["value"]
                
            return formatted

        # Handle list of TrackedFields (like skills, experience)
        if isinstance(field_data, list):
            return [self._format_field(item) for item in field_data]

        return field_data

    def _collect_provenance(self, profile: InternalCandidateProfile) -> List[Dict[str, Any]]:
        provenance_list = []
        
        def add_prov(field_obj: Any, name: str):
            if field_obj and hasattr(field_obj, "provenance") and field_obj.provenance:
                p = field_obj.provenance
                provenance_list.append({
                    "field": name,
                    "source": p.source,
                    "method": p.method
                })

        # Scalars
        add_prov(profile.full_name, "full_name")
        add_prov(profile.location, "location")
        add_prov(profile.links, "links")
        add_prov(profile.headline, "headline")
        add_prov(profile.years_experience, "years_experience")
        
        # Lists
        for item in profile.emails:
            add_prov(item, "emails")
        for item in profile.phones:
            add_prov(item, "phones")
        for item in profile.skills:
            add_prov(item, "skills")
        for item in profile.experience:
            add_prov(item, "experience")
        for item in profile.education:
            add_prov(item, "education")
            
        return provenance_list

    def project(self, profile: InternalCandidateProfile) -> Dict[str, Any]:
        """
        Transforms the canonical profile into the schema-valid projected output dictionary.
        """
        internal_dict = profile.model_dump()
        projected_output = {}

        for field_def in self.config.fields:
            out_key = field_def["path"]
            internal_key = field_def.get("from", out_key)
            is_required = field_def.get("required", False)

            # 1. Check for computed fields
            if "computed" in field_def:
                computed_type = field_def["computed"]
                if computed_type == "calculate_experience_count":
                    raw_val = len(internal_dict.get("experience", []))
                elif computed_type == "calculate_skills_count":
                    raw_val = len(internal_dict.get("skills", []))
                else:
                    raw_val = None
            else:
                # Standard path extraction
                raw_val = self._extract_value(internal_dict, internal_key)

            # 2. Handle missing values
            if raw_val is None or (isinstance(raw_val, list) and len(raw_val) == 0):
                if is_required and self.config.on_missing == "error":
                    raise ValueError(f"Validation Error: Required field '{out_key}' is missing.")
                elif self.config.on_missing == "omit":
                    continue
                else:  # "null"
                    if out_key in ["emails", "phones", "skills", "experience", "education"]:
                        projected_output[out_key] = []
                    elif out_key in ["location", "links"]:
                        projected_output[out_key] = None
                    else:
                        projected_output[out_key] = None
                continue

            # 3. Format field based on type
            projected_output[out_key] = self._format_field_by_type(raw_val, out_key)

        # Inject overall confidence and provenance array
        projected_output["provenance"] = self._collect_provenance(profile)
        projected_output["overall_confidence"] = float(profile.overall_confidence)
            
        return projected_output