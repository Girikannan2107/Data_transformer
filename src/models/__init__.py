# src/models/__init__.py
from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict
from datetime import datetime
from src.models.domain_fields import (
    Provenance,
    DomainField,
    NameField,
    EmailField,
    PhoneField,
    SkillField,
    LocationField,
    HeadlineField,
    LinkField,
    ExperienceField,
    EducationField
)

# Alias for backward compatibility
TrackedField = DomainField

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
# Extraction Models
# ---------------------------------------------------------

class RawCandidateRecord(BaseModel):
    candidate_id: str
    source: str
    raw_data: Dict[str, Any]
    extraction_timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

# ---------------------------------------------------------
# Internal Canonical Profile
# ---------------------------------------------------------

class InternalCandidateProfile(BaseModel):
    """
    The 'fat' internal record. Every field is wrapped in a TrackedField (DomainField).
    This acts as the absolute source of truth before the Projection Layer 
    flattens it out for final JSON output.
    """
    candidate_id: str
    
    # Scalars (Highest confidence wins during merge)
    full_name: Optional[NameField] = None
    location: Optional[LocationField] = None      # value: LocationData
    links: Optional[LinkField] = None             # value: LinksData
    headline: Optional[HeadlineField] = None
    years_experience: Optional[DomainField] = None
    
    # Arrays (Unioned and deduplicated during merge)
    emails: List[EmailField] = Field(default_factory=list)              # value: str
    phones: List[PhoneField] = Field(default_factory=list)              # value: str
    skills: List[SkillField] = Field(default_factory=list)              # value: str
    experience: List[ExperienceField] = Field(default_factory=list)      # value: ExperienceData
    education: List[EducationField] = Field(default_factory=list)        # value: EducationData
    
    overall_confidence: float = 0.0

    class Config:
        arbitrary_types_allowed = True
