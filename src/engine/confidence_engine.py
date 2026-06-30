# src/engine/confidence_engine.py
import re
import logging
from typing import List, Any
from src.models import InternalCandidateProfile, TrackedField
from src.models.domain_fields import EmailField, PhoneField

logger = logging.getLogger(__name__)

class ConfidenceEngine:
    """
    Calculates field-level and overall candidate confidence scores.
    Uses source reliability, agreement bonuses, conflict penalties,
    and validation outcomes. Traces history inside confidence_evolution.
    """

    @staticmethod
    def calculate_field_confidence(field: TrackedField, field_type: str) -> TrackedField:
        if not field:
            return field
            
        base_score = field.provenance.confidence
        evolution = [f"Base extraction confidence: {base_score:.2f} ({field.provenance.source})"]
        
        # 1. Agreement Bonus
        agreement_bonus = 0.0
        agreement_count = field.provenance.agreement_count
        if agreement_count > 1:
            agreement_bonus = min(0.20, 0.05 * (agreement_count - 1))
            evolution.append(f"Agreement Bonus: +{agreement_bonus:.2f} ({agreement_count} matching sources)")
            
        # 2. Conflict Penalty
        conflict_penalty = 0.0
        rejected_count = len(field.provenance.rejected_sources)
        if rejected_count > 0:
            conflict_penalty = max(-0.15, -0.05 * rejected_count)
            evolution.append(f"Conflict Penalty: {conflict_penalty:.2f} ({rejected_count} conflicting sources)")
            
        # 3. Validation Adjustments
        validation_adj = 0.0
        val_str = str(field.value)
        
        if field_type == "emails" or isinstance(field, EmailField):
            # Email structure check
            email_regex = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
            if re.match(email_regex, val_str):
                validation_adj = 0.05
                evolution.append(f"Validation Bonus: +0.05 (Valid email structure)")
            else:
                validation_adj = -0.20
                evolution.append(f"Validation Penalty: -0.20 (Invalid email structure)")
                
        elif field_type == "phones" or isinstance(field, PhoneField):
            # E164 check
            if "E164_Format" in field.provenance.normalization_applied:
                validation_adj = 0.10
                evolution.append(f"Validation Bonus: +0.10 (Valid E164 phone format)")
            else:
                validation_adj = -0.30
                evolution.append(f"Validation Penalty: -0.30 (Invalid or un-parseable phone format)")

        # 4. Normalization success checks (e.g. Fuzzy matches)
        norm_penalty = 0.0
        for norm in field.provenance.normalization_applied:
            if "Fuzzy_Match" in norm:
                # e.g., "Fuzzy_Match_90pct"
                try:
                    pct_str = norm.split('_')[-1].replace('pct', '')
                    pct = float(pct_str)
                    if pct < 100:
                        norm_penalty = -((100 - pct) / 100.0) * 0.10
                        evolution.append(f"Fuzzy Normalization Adjustment: {norm_penalty:.2f} ({pct}% match similarity)")
                except Exception:
                    pass

        # Final field confidence calculation
        final_score = base_score + agreement_bonus + conflict_penalty + validation_adj + norm_penalty
        final_score = round(max(0.0, min(1.0, final_score)), 2)
        
        field.confidence = final_score
        field.provenance.confidence = final_score
        field.provenance.confidence_evolution = evolution
        
        return field

    @staticmethod
    def evaluate(profile: InternalCandidateProfile) -> InternalCandidateProfile:
        """
        Evaluate confidence scores for all fields and determine the overall profile confidence.
        """
        logger.info(f"Evaluating candidate confidences for {profile.candidate_id}...")
        
        fields_to_eval = []
        
        if profile.full_name:
            profile.full_name = ConfidenceEngine.calculate_field_confidence(profile.full_name, "full_name")
            fields_to_eval.append(profile.full_name)
            
        if profile.location:
            profile.location = ConfidenceEngine.calculate_field_confidence(profile.location, "location")
            fields_to_eval.append(profile.location)
            
        if profile.links:
            profile.links = ConfidenceEngine.calculate_field_confidence(profile.links, "links")
            fields_to_eval.append(profile.links)
            
        if profile.headline:
            profile.headline = ConfidenceEngine.calculate_field_confidence(profile.headline, "headline")
            fields_to_eval.append(profile.headline)
            
        if profile.years_experience:
            profile.years_experience = ConfidenceEngine.calculate_field_confidence(profile.years_experience, "years_experience")
            fields_to_eval.append(profile.years_experience)

        # Evaluate Array Lists
        for i, e in enumerate(profile.emails):
            profile.emails[i] = ConfidenceEngine.calculate_field_confidence(e, "emails")
            fields_to_eval.append(profile.emails[i])
            
        for i, ph in enumerate(profile.phones):
            profile.phones[i] = ConfidenceEngine.calculate_field_confidence(ph, "phones")
            fields_to_eval.append(profile.phones[i])
            
        for i, sk in enumerate(profile.skills):
            profile.skills[i] = ConfidenceEngine.calculate_field_confidence(sk, "skills")
            fields_to_eval.append(profile.skills[i])
            
        for i, exp in enumerate(profile.experience):
            profile.experience[i] = ConfidenceEngine.calculate_field_confidence(exp, "experience")
            fields_to_eval.append(profile.experience[i])
            
        for i, edu in enumerate(profile.education):
            profile.education[i] = ConfidenceEngine.calculate_field_confidence(edu, "education")
            fields_to_eval.append(profile.education[i])

        # Compute Overall Profile Confidence (Average of fields + Multi-source bonus)
        if not fields_to_eval:
            profile.overall_confidence = 0.0
            return profile
            
        total_conf = sum(f.confidence for f in fields_to_eval)
        avg_conf = total_conf / len(fields_to_eval)
        
        # Calculate distinct sources participating in overall merge
        distinct_sources = set()
        for f in fields_to_eval:
            distinct_sources.add(f.provenance.source)
            for rej in f.provenance.rejected_sources:
                distinct_sources.add(rej.get("source"))
                
        # Overall multi-source agreement bonus: +0.05 if data represents > 1 source
        source_bonus = 0.05 if len(distinct_sources) > 1 else 0.0
        
        profile.overall_confidence = round(max(0.0, min(1.0, avg_conf + source_bonus)), 2)
        logger.debug(f"Computed overall candidate confidence: {profile.overall_confidence} "
                     f"(Average: {avg_conf:.2f}, Source Bonus: +{source_bonus:.2f})")
        
        return profile
