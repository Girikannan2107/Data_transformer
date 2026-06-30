# src/engine/entity_resolution.py
import logging
from typing import List, Dict, Any, Callable
from rapidfuzz import fuzz
from src.models.domain_fields import DomainField, SkillField, ExperienceField, EducationField
from src.models import ExperienceData, EducationData

logger = logging.getLogger(__name__)

class EntityResolutionGraph:
    """
    Groups extracted fields into match clusters without merging them.
    Supports Exact Matching, Rule Mapping, and RapidFuzz scoring.
    """
    
    @staticmethod
    def group_scalars(profiles: List[Any]) -> Dict[str, List[DomainField]]:
        """
        Groups single scalar fields from all incoming profiles by field type.
        """
        groups = {
            "full_name": [],
            "location": [],
            "links": [],
            "headline": [],
            "years_experience": []
        }
        
        for p in profiles:
            if p.full_name: groups["full_name"].append(p.full_name)
            if p.location: groups["location"].append(p.location)
            if p.links: groups["links"].append(p.links)
            if p.headline: groups["headline"].append(p.headline)
            if p.years_experience: groups["years_experience"].append(p.years_experience)
            
        return {k: v for k, v in groups.items() if v}

    @staticmethod
    def group_array_fields(fields: List[DomainField], key_type: str) -> List[List[DomainField]]:
        """
        Partitions a flat list of TrackedFields into clusters of matching items.
        """
        clusters: List[List[DomainField]] = []
        
        for field in fields:
            if field is None or field.value is None:
                continue
            
            # Find an existing cluster that matches this field
            matched = False
            for cluster in clusters:
                if EntityResolutionGraph._are_matching(field, cluster[0], key_type):
                    cluster.append(field)
                    matched = True
                    break
            
            if not matched:
                clusters.append([field])
                
        return clusters

    @staticmethod
    def _are_matching(f1: DomainField, f2: DomainField, key_type: str) -> bool:
        v1 = f1.value
        v2 = f2.value
        
        if type(v1) != type(v2):
            return False
            
        # Exact Matching fields
        if key_type in ["emails", "phones", "links"]:
            return str(v1).lower().strip() == str(v2).lower().strip()
            
        # Fuzzy Matching fields (Skills)
        if key_type == "skills":
            s1 = str(v1).lower().strip()
            s2 = str(v2).lower().strip()
            if s1 == s2:
                return True
            # RapidFuzz match threshold >= 85
            score = fuzz.WRatio(s1, s2)
            return score >= 85

        # Composite structures (Experience)
        if key_type == "experience" and isinstance(v1, ExperienceData) and isinstance(v2, ExperienceData):
            comp1 = str(v1.company).lower().strip()
            comp2 = str(v2.company).lower().strip()
            title1 = str(v1.title).lower().strip()
            title2 = str(v2.title).lower().strip()
            # Fuzzy match company and title
            company_match = (comp1 == comp2) or (fuzz.WRatio(comp1, comp2) >= 85)
            title_match = (title1 == title2) or (fuzz.WRatio(title1, title2) >= 85)
            return company_match and title_match

        # Composite structures (Education)
        if key_type == "education" and isinstance(v1, EducationData) and isinstance(v2, EducationData):
            inst1 = str(v1.institution).lower().strip()
            inst2 = str(v2.institution).lower().strip()
            return (inst1 == inst2) or (fuzz.WRatio(inst1, inst2) >= 85)

        # Fallback exact string match
        return str(v1).lower().strip() == str(v2).lower().strip()