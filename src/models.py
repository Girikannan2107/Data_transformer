from pydantic import BaseModel, Field
from typing import List, Optional, Any
from datetime import datetime

# ---------------------------------------------------------
# Provenance & Tracking Models
# ---------------------------------------------------------


class Provenance(BaseModel):
    field: Optional[str] = None
    source: str
    method: str
    confidence: float
    # Add this line below to fix your error:
    normalization_applied: Optional[str] = None
class TrackedField(BaseModel):
    value: Any
    provenance: Provenance

# ---------------------------------------------------------
# Sub-Schemas (Based on the Assignment Requirements)
# ---------------------------------------------------------

class LocationData(BaseModel):
    city: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None  # ISO-3166 alpha-2

class LinksData(BaseModel):
    linkedin: Optional[str] = None
    github: Optional[str] = None
    portfolio: Optional[str] = None
    other: List[str] = []

class ExperienceData(BaseModel):
    company: str
    title: str
    start: Optional[str] = None  # YYYY-MM
    end: Optional[str] = None    # YYYY-MM
    summary: Optional[str] = None

class EducationData(BaseModel):
    institution: str
    degree: Optional[str] = None
    field: Optional[str] = None
    end_year: Optional[str] = None

# ---------------------------------------------------------
# Internal Canonical Profile
# ---------------------------------------------------------

class InternalCandidateProfile(BaseModel):
    """
    The 'fat' internal record. Every field is wrapped in a TrackedField.
    This acts as the absolute source of truth before the Projection Layer 
    flattens it out for final JSON output.
    """
    candidate_id: str
    
    # Scalars (Highest confidence wins during merge)
    full_name: Optional[TrackedField] = None
    location: Optional[TrackedField] = None      # value: LocationData
    links: Optional[TrackedField] = None         # value: LinksData
    headline: Optional[TrackedField] = None
    years_experience: Optional[TrackedField] = None
    
    # Arrays (Unioned and deduplicated during merge)
    emails: List[TrackedField] = []              # value: str
    phones: List[TrackedField] = []              # value: str
    skills: List[TrackedField] = []              # value: str
    experience: List[TrackedField] = []          # value: ExperienceData
    education: List[TrackedField] = []           # value: EducationData
    
    overall_confidence: float = 0.0

    class Config:
        arbitrary_types_allowed = True