# src/models/domain_fields.py
from pydantic import BaseModel, Field
from typing import Any, Optional, List, Dict
from datetime import datetime

class Provenance(BaseModel):
    field: Optional[str] = None
    source: str
    method: str
    confidence: float
    normalization_applied: List[str] = Field(default_factory=list)
    confidence_evolution: List[str] = Field(default_factory=list)
    agreement_count: int = 1
    supporting_sources: List[str] = Field(default_factory=list)
    rejected_sources: List[Dict[str, Any]] = Field(default_factory=list)
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    merge_decision: Optional[str] = None

class DomainField(BaseModel):
    raw_value: Any = None
    canonical_value: Optional[Any] = None
    value: Any = None  # Backward compatibility with TrackedField
    confidence: float = 0.0
    provenance: Provenance
    validation_status: str = "PENDING"

    def model_post_init(self, __context: Any) -> None:
        # Backward compatibility mapper
        if self.raw_value is None and self.value is not None:
            self.raw_value = self.value
        if self.value is None:
            self.value = self.canonical_value if self.canonical_value is not None else self.raw_value

    def update_canonical(self, canonical_val: Any, norm_method: Optional[str] = None):
        self.canonical_value = canonical_val
        self.value = canonical_val
        if norm_method and norm_method not in self.provenance.normalization_applied:
            self.provenance.normalization_applied.append(norm_method)

class NameField(DomainField): pass
class EmailField(DomainField): pass
class PhoneField(DomainField): pass
class SkillField(DomainField): pass
class LocationField(DomainField): pass
class HeadlineField(DomainField): pass
class LinkField(DomainField): pass
class ExperienceField(DomainField): pass
class EducationField(DomainField): pass