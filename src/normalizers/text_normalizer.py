# src/normalizers/text_normalizer.py
import re
import logging
import phonenumbers
import pycountry
from dateutil import parser
from rapidfuzz import process, fuzz
from typing import Optional, List
from src.models import TrackedField, ExperienceData, EducationData

logger = logging.getLogger(__name__)

class Normalizer:
    """
    Deterministic pure functions to format and canonicalize data.
    These methods NEVER modify confidence, perform validation, or merge records.
    They append tracking info to the normalization_applied list.
    """

    CANONICAL_SKILLS = ["Machine Learning", "Python", "PyTorch", "React", "JavaScript", "Data Science"]
    SKILL_ALIASES = {"ml": "Machine Learning", "js": "JavaScript", "node": "Node.js"}

    @staticmethod
    def normalize_name(field: TrackedField) -> TrackedField:
        if not field or not field.value:
            return field
        clean_name = re.sub(r'[^a-zA-Z\s\.\-]', '', str(field.value))
        clean_name = ' '.join(clean_name.split()).title()
        field.update_canonical(clean_name, "TitleCase_CleanWhitespace")
        return field

    @staticmethod
    def normalize_email(field: TrackedField) -> TrackedField:
        if not field or not field.value:
            return field
        clean_email = str(field.value).strip().lower()
        field.update_canonical(clean_email, "Lowercase_Strip")
        return field

    @staticmethod
    def normalize_phone(field: TrackedField, default_region="US") -> TrackedField:
        if not field or not field.value:
            return field
        val = str(field.value).strip()
        try:
            parsed = phonenumbers.parse(val, default_region)
            e164_val = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
            field.update_canonical(e164_val, "E164_Format")
        except Exception:
            # If parsing fails, do NOT change confidence or fail, just keep the raw value
            field.update_canonical(val, "Parse_Attempt_Failed")
        return field

    @staticmethod
    def normalize_skill(field: TrackedField) -> TrackedField:
        if not field or not field.value:
            return field
        val_lower = str(field.value).lower().strip()
        
        # 1. Check exact Alias Mapping (e.g., "ml" -> "Machine Learning")
        if val_lower in Normalizer.SKILL_ALIASES:
            field.update_canonical(Normalizer.SKILL_ALIASES[val_lower], "Canonical_Alias_Map")
            return field

        # 2. Fuzzy Match against Canonical Dictionary
        match = process.extractOne(val_lower, Normalizer.CANONICAL_SKILLS, scorer=fuzz.WRatio)
        if match and match[1] >= 80:  # 80% similarity threshold
            field.update_canonical(match[0], f"Fuzzy_Match_{match[1]:.0f}pct")
            return field

        # 3. Fallback: Title Case it
        field.update_canonical(val_lower.title(), "TitleCase_Fallback")
        return field

    @staticmethod
    def normalize_date(date_str: str) -> Optional[str]:
        """Helper to convert dates to YYYY-MM."""
        if not date_str or str(date_str).lower() in ["present", "current", "now"]:
            return None
        try:
            dt = parser.parse(str(date_str), fuzzy=True)
            return dt.strftime("%Y-%m")
        except Exception:
            return str(date_str).strip()

    @staticmethod
    def normalize_country(country_name: str) -> Optional[str]:
        """Helper to convert country names to ISO-3166 alpha-2."""
        if not country_name:
            return None
        name_str = str(country_name).strip()
        try:
            country = pycountry.countries.lookup(name_str)
            return country.alpha_2
        except LookupError:
            try:
                results = pycountry.countries.search_fuzzy(name_str)
                if results:
                    return results[0].alpha_2
            except Exception:
                pass
        return name_str

    @staticmethod
    def normalize_experience(field: TrackedField) -> TrackedField:
        """Normalizes experience fields (company, title, and dates)."""
        if not field or not field.value or not isinstance(field.value, ExperienceData):
            return field
        
        exp = field.value
        norm_company = ' '.join(str(exp.company).split()).title()
        norm_title = ' '.join(str(exp.title).split()).title()
        norm_start = Normalizer.normalize_date(exp.start) if exp.start else None
        norm_end = Normalizer.normalize_date(exp.end) if exp.end else None
        
        norm_exp = ExperienceData(
            company=norm_company,
            title=norm_title,
            start=norm_start,
            end=norm_end,
            summary=exp.summary
        )
        field.update_canonical(norm_exp, "Experience_Standardization")
        return field

    @staticmethod
    def normalize_education(field: TrackedField) -> TrackedField:
        """Normalizes education fields (institution, degree, and dates)."""
        if not field or not field.value or not isinstance(field.value, EducationData):
            return field
        
        edu = field.value
        norm_inst = ' '.join(str(edu.institution).split()).title()
        norm_degree = ' '.join(str(edu.degree).split()).title() if edu.degree else None
        norm_field = ' '.join(str(edu.field).split()).title() if edu.field else None
        
        norm_edu = EducationData(
            institution=norm_inst,
            degree=norm_degree,
            field=norm_field,
            end_year=str(edu.end_year).strip() if edu.end_year else None
        )
        field.update_canonical(norm_edu, "Education_Standardization")
        return field