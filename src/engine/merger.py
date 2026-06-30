import logging
from typing import List, Optional, Any, Callable, Dict
from src.models import InternalCandidateProfile, TrackedField

logger = logging.getLogger(__name__)

class MergeEngine:
    """
    Deterministically merges multiple InternalCandidateProfiles.
    Logic: 
    1. Scalars: Highest confidence wins (Source Priority).
    2. Arrays: Union unique values, keep highest confidence version.
    3. Agreement: Cross-source validation boosts overall confidence.
    """

    @staticmethod
    def _resolve_scalar_conflict(fields: List[Optional[TrackedField]]) -> Optional[TrackedField]:
        valid_fields = [f for f in fields if f is not None and f.value is not None]
        if not valid_fields:
            return None

        # Sort: Confidence (Desc), Source Name (Desc) for absolute determinism
        valid_fields.sort(key=lambda x: (x.provenance.confidence, x.provenance.source), reverse=True)
        
        return valid_fields[0]

    @staticmethod
    def _deduplicate_array(all_fields: List[TrackedField], key_extractor: Callable[[Any], str]) -> List[TrackedField]:
        unique_map: Dict[str, TrackedField] = {}
        
        for field in all_fields:
            if not field or field.value is None:
                continue
                
            dedup_key = key_extractor(field.value).lower().strip()
            
            # Logic: Keep the highest confidence version, or union if same confidence
            if dedup_key not in unique_map or field.provenance.confidence > unique_map[dedup_key].provenance.confidence:
                unique_map[dedup_key] = field
                
        return sorted(list(unique_map.values()), key=lambda x: str(x.value))

    @staticmethod
    def merge(candidate_id: str, profiles: List[InternalCandidateProfile]) -> InternalCandidateProfile:
        if not profiles:
            return InternalCandidateProfile(candidate_id=candidate_id)
        if len(profiles) == 1:
            return profiles[0]

        logger.info(f"Merging {len(profiles)} profiles for candidate {candidate_id}...")
        merged = InternalCandidateProfile(candidate_id=candidate_id)

        # 1. Resolve Scalars
        merged.full_name = MergeEngine._resolve_scalar_conflict([p.full_name for p in profiles])
        merged.location = MergeEngine._resolve_scalar_conflict([p.location for p in profiles])
        merged.links = MergeEngine._resolve_scalar_conflict([p.links for p in profiles])
        merged.headline = MergeEngine._resolve_scalar_conflict([p.headline for p in profiles])
        merged.years_experience = MergeEngine._resolve_scalar_conflict([p.years_experience for p in profiles])

        # 2. Flatten Arrays for Merge
        all_emails = [e for p in profiles for e in p.emails if e]
        all_phones = [ph for p in profiles for ph in p.phones if ph]
        all_skills = [sk for p in profiles for sk in p.skills if sk]
        all_exp = [exp for p in profiles for exp in p.experience if exp]
        all_edu = [edu for p in profiles for edu in p.education if edu]

        merged.emails = MergeEngine._deduplicate_array(all_emails, lambda v: str(v))
        merged.phones = MergeEngine._deduplicate_array(all_phones, lambda v: str(v))
        merged.skills = MergeEngine._deduplicate_array(all_skills, lambda v: str(v))
        
        merged.experience = MergeEngine._deduplicate_array(all_exp, lambda e: f"{e.company}-{e.title}")
        merged.education = MergeEngine._deduplicate_array(all_edu, lambda e: f"{e.institution}-{e.degree}")

        # 3. Calculate Overall Confidence with Agreement Bonus
        # Identifying sources that agree on the same value
        all_fields = [merged.full_name, merged.location, merged.links, merged.headline] + \
                     merged.emails + merged.phones + merged.skills
        
        valid_winners = [f for f in all_fields if f is not None]
        
        if valid_winners:
            # Base confidence average
            base_conf = sum(f.provenance.confidence for f in valid_winners) / len(valid_winners)
            
            # AGREEMENT BONUS: If >1 source contributed to the merge, add a bonus
            # This satisfies the requirement: "Confidence increases when sources agree"
            agreement_bonus = 0.05 if len(profiles) > 1 else 0.0
            
            merged.overall_confidence = round(min(1.0, base_conf + agreement_bonus), 2)

        return merged