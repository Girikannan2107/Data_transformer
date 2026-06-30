# src/engine/merger.py
import logging
from typing import List, Optional, Dict, Any
from src.models import InternalCandidateProfile, TrackedField
from src.engine.entity_resolution import EntityResolutionGraph

logger = logging.getLogger(__name__)

class MergeEngine:
    """
    Weighted Aggregation Merge Engine.
    Combines conflicting and matching values into canonical fields, preserving
    all alternate values, supporting sources, and merge explanations.
    """

    @staticmethod
    def aggregate(field_group: List[TrackedField], field_name: str) -> Optional[TrackedField]:
        if not field_group:
            return None
            
        # Group by canonical/raw value to count support and compute weighted scores
        value_groups = {}
        for f in field_group:
            if f is None or f.value is None:
                continue
            val_key = str(f.value)
            if val_key not in value_groups:
                value_groups[val_key] = {"value": f.value, "fields": []}
            value_groups[val_key]["fields"].append(f)
            
        if not value_groups:
            return None
            
        # Compute total confidence score for each unique value
        scored_values = []
        for val_key, g in value_groups.items():
            total_confidence = sum(f.provenance.confidence for f in g["fields"])
            scored_values.append((total_confidence, val_key, g["value"], g["fields"]))
            
        # Sort by total_confidence (descending), then val_key (descending) to be fully deterministic
        scored_values.sort(key=lambda x: (x[0], x[1]), reverse=True)
        
        winning_score, winning_key, winning_val, winning_fields = scored_values[0]
        
        # Choose primary winner (highest individual confidence source)
        winning_fields.sort(key=lambda x: x.provenance.confidence, reverse=True)
        primary_winner = winning_fields[0]
        
        # Construct the merged domain field
        merged_field = primary_winner.__class__(
            raw_value=primary_winner.raw_value,
            canonical_value=winning_val if primary_winner.canonical_value is not None else None,
            value=winning_val,
            confidence=primary_winner.provenance.confidence,  # Will be finalized by Confidence Engine
            provenance=primary_winner.provenance.model_copy()
        )
        
        # Accumulate all normalizations applied
        norms = set()
        for wf in winning_fields:
            norms.update(wf.provenance.normalization_applied)
        merged_field.provenance.normalization_applied = sorted(list(norms))
        
        # Set supporting sources and agreement details
        supporting_sources = [wf.provenance.source for wf in winning_fields]
        merged_field.provenance.supporting_sources = supporting_sources
        merged_field.provenance.agreement_count = len(winning_fields)
        
        # Set rejected sources
        rejected_sources = []
        for score, key, val, fields in scored_values[1:]:
            for rf in fields:
                rejected_sources.append({
                    "value": str(val),
                    "source": rf.provenance.source,
                    "method": rf.provenance.method,
                    "confidence": rf.provenance.confidence
                })
        merged_field.provenance.rejected_sources = rejected_sources
        
        # Construct merge decision
        merged_field.provenance.merge_decision = (
            f"Selected value '{winning_val}' with aggregate confidence score {winning_score:.2f} "
            f"supported by {len(winning_fields)} source(s) ({', '.join(supporting_sources)}). "
            f"Rejected {len(rejected_sources)} conflicting evidence source(s)."
        )
        
        return merged_field

    @staticmethod
    def merge(candidate_id: str, profiles: List[InternalCandidateProfile]) -> InternalCandidateProfile:
        if not profiles:
            return InternalCandidateProfile(candidate_id=candidate_id)
            
        merged = InternalCandidateProfile(candidate_id=candidate_id)
        
        # 1. Resolve Scalars (Group by scalar name and aggregate)
        scalar_groups = EntityResolutionGraph.group_scalars(profiles)
        
        if "full_name" in scalar_groups:
            merged.full_name = MergeEngine.aggregate(scalar_groups["full_name"], "full_name")
        if "location" in scalar_groups:
            merged.location = MergeEngine.aggregate(scalar_groups["location"], "location")
        if "links" in scalar_groups:
            merged.links = MergeEngine.aggregate(scalar_groups["links"], "links")
        if "headline" in scalar_groups:
            merged.headline = MergeEngine.aggregate(scalar_groups["headline"], "headline")
        if "years_experience" in scalar_groups:
            merged.years_experience = MergeEngine.aggregate(scalar_groups["years_experience"], "years_experience")
            
        # 2. Group and Resolve Arrays
        all_emails = [e for p in profiles for e in p.emails if e]
        all_phones = [ph for p in profiles for ph in p.phones if ph]
        all_skills = [sk for p in profiles for sk in p.skills if sk]
        all_exp = [exp for p in profiles for exp in p.experience if exp]
        all_edu = [edu for p in profiles for edu in p.education if edu]
        
        email_clusters = EntityResolutionGraph.group_array_fields(all_emails, "emails")
        merged.emails = [MergeEngine.aggregate(c, "emails") for c in email_clusters if c]
        
        phone_clusters = EntityResolutionGraph.group_array_fields(all_phones, "phones")
        merged.phones = [MergeEngine.aggregate(c, "phones") for c in phone_clusters if c]
        
        skill_clusters = EntityResolutionGraph.group_array_fields(all_skills, "skills")
        merged.skills = [MergeEngine.aggregate(c, "skills") for c in skill_clusters if c]
        
        exp_clusters = EntityResolutionGraph.group_array_fields(all_exp, "experience")
        merged.experience = [MergeEngine.aggregate(c, "experience") for c in exp_clusters if c]
        
        edu_clusters = EntityResolutionGraph.group_array_fields(all_edu, "education")
        merged.education = [MergeEngine.aggregate(c, "education") for c in edu_clusters if c]
        
        return merged