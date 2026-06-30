# src/engine/business_rules.py
import logging
from typing import List, Any, Dict
from src.models import InternalCandidateProfile, TrackedField
from src.core.context import PipelineContext

logger = logging.getLogger(__name__)

class BusinessRuleEngine:
    """
    Applies configurable business rules to the canonical candidate profile.
    Filters elements by minimum confidence, applies blacklists, and enforces required checks.
    """

    @staticmethod
    def apply(profile: InternalCandidateProfile, context: PipelineContext) -> InternalCandidateProfile:
        logger.info(f"Applying business rules for candidate {profile.candidate_id}...")
        
        # Read business rules from context configuration
        rules = context.config.get("business_rules", {})
        min_field_conf = rules.get("min_field_confidence", 0.0)
        skill_blacklist = [s.lower().strip() for s in rules.get("skill_blacklist", [])]
        required_fields = rules.get("required_fields", [])
        
        # 1. Filter out low-confidence array items
        if min_field_conf > 0.0:
            original_email_count = len(profile.emails)
            profile.emails = [e for e in profile.emails if e.confidence >= min_field_conf]
            filtered_emails = original_email_count - len(profile.emails)
            if filtered_emails > 0:
                logger.warning(f"Business Rules: Filtered out {filtered_emails} email(s) below confidence threshold {min_field_conf}")

            original_phone_count = len(profile.phones)
            profile.phones = [p for p in profile.phones if p.confidence >= min_field_conf]
            filtered_phones = original_phone_count - len(profile.phones)
            if filtered_phones > 0:
                logger.warning(f"Business Rules: Filtered out {filtered_phones} phone(s) below confidence threshold {min_field_conf}")

            original_skill_count = len(profile.skills)
            profile.skills = [s for s in profile.skills if s.confidence >= min_field_conf]
            filtered_skills = original_skill_count - len(profile.skills)
            if filtered_skills > 0:
                logger.warning(f"Business Rules: Filtered out {filtered_skills} skill(s) below confidence threshold {min_field_conf}")

            # Check scalars
            for scalar_name in ["full_name", "location", "links", "headline", "years_experience"]:
                field_val = getattr(profile, scalar_name)
                if field_val and field_val.confidence < min_field_conf:
                    logger.warning(f"Business Rules: Clearing scalar field '{scalar_name}' because confidence {field_val.confidence} < threshold {min_field_conf}")
                    setattr(profile, scalar_name, None)

        # 2. Apply Skill Blacklist
        if skill_blacklist:
            original_skill_count = len(profile.skills)
            profile.skills = [s for s in profile.skills if str(s.value).lower().strip() not in skill_blacklist]
            blacklisted_count = original_skill_count - len(profile.skills)
            if blacklisted_count > 0:
                logger.warning(f"Business Rules: Filtered out {blacklisted_count} skill(s) due to keyword blacklist.")

        # 3. Check Required Fields & Log Validation Metrics
        missing_required = []
        for req_field in required_fields:
            val = getattr(profile, req_field, None)
            if val is None or (isinstance(val, list) and len(val) == 0):
                missing_required.append(req_field)
                
        if missing_required:
            logger.error(f"Business Rules: Candidate {profile.candidate_id} is missing required fields: {missing_required}")
            context.log_metric("business_rules_validation_failed", True)
            context.log_metric("missing_fields", missing_required)
        else:
            context.log_metric("business_rules_validation_failed", False)

        return profile
