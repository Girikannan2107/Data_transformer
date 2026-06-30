import re
import logging
import phonenumbers
import pycountry
from dateutil import parser
from rapidfuzz import process, fuzz
from src.models import TrackedField

logger = logging.getLogger(__name__)

class Normalizer:
    """
    Deterministic pure functions to clean, format, and canonicalize data.
    Every function updates the `normalization_applied` provenance metadata.
    """

    # A mock dictionary for canonical skills. In production, this would be loaded from a DB.
    CANONICAL_SKILLS = ["Machine Learning", "Python", "PyTorch", "React", "JavaScript", "Data Science"]
    SKILL_ALIASES = {"ml": "Machine Learning", "js": "JavaScript", "node": "Node.js"}

    @staticmethod
    def normalize_name(field: TrackedField) -> TrackedField:
        if not field or not field.value: return field
        # Remove special characters, reduce multiple spaces to one, apply Title Case
        clean_name = re.sub(r'[^a-zA-Z\s\.\-]', '', field.value)
        clean_name = ' '.join(clean_name.split()).title()
        
        field.value = clean_name
        field.provenance.normalization_applied = "TitleCase_CleanWhitespace"
        return field

    @staticmethod
    def normalize_email(field: TrackedField) -> TrackedField:
        if not field or not field.value: return field
        field.value = str(field.value).strip().lower()
        field.provenance.normalization_applied = "Lowercase_Strip"
        return field

    @staticmethod
    def normalize_phone(field: TrackedField, default_region="US") -> TrackedField:
        if not field or not field.value: return field
        try:
            parsed = phonenumbers.parse(field.value, default_region)
            if phonenumbers.is_valid_number(parsed):
                # E.164 Format: +14155552671
                field.value = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
                field.provenance.normalization_applied = "E164_Format"
                # Validation Boost! A perfectly parsed phone number is highly reliable.
                field.provenance.confidence = min(1.0, field.provenance.confidence + 0.1)
            else:
                # Penalize invalid formats
                field.provenance.confidence *= 0.5 
                field.provenance.normalization_applied = "Invalid_Format_Penalty"
        except phonenumbers.NumberParseException:
            field.provenance.confidence *= 0.5
            field.provenance.normalization_applied = "Parse_Failure_Penalty"
        return field

    @staticmethod
    def normalize_skill(field: TrackedField) -> TrackedField:
        if not field or not field.value: return field
        val_lower = str(field.value).lower().strip()
        
        # 1. Check exact Alias Mapping (e.g., "ml" -> "Machine Learning")
        if val_lower in Normalizer.SKILL_ALIASES:
            field.value = Normalizer.SKILL_ALIASES[val_lower]
            field.provenance.normalization_applied = "Canonical_Alias_Map"
            return field

        # 2. Fuzzy Match against Canonical Dictionary
        # WRatio handles slight misspellings and partial string matches
        match = process.extractOne(val_lower, Normalizer.CANONICAL_SKILLS, scorer=fuzz.WRatio)
        if match and match[1] >= 85:  # 85% similarity threshold
            field.value = match[0]
            field.provenance.normalization_applied = f"Fuzzy_Match ({match[1]:.1f}%)"
            return field

        # 3. Fallback: If it's a new, unknown skill, just Title Case it
        field.value = val_lower.title()
        field.provenance.normalization_applied = "TitleCase_Fallback"
        return field

    @staticmethod
    def normalize_date(date_str: str) -> str:
        """Helper to convert dates to YYYY-MM. Does not take a TrackedField directly."""
        if not date_str or str(date_str).lower() == "present":
            return None
        try:
            dt = parser.parse(date_str, fuzzy=True)
            return dt.strftime("%Y-%m")
        except Exception:
            return date_str

    @staticmethod
    def normalize_country(country_name: str) -> str:
        """Helper to convert country names to ISO-3166 alpha-2."""
        if not country_name: return None
        try:
            # Try exact lookup (e.g., "United States" -> "US")
            country = pycountry.countries.lookup(country_name)
            return country.alpha_2
        except LookupError:
            try:
                # Try fuzzy lookup (e.g., "America" -> "US")
                results = pycountry.countries.search_fuzzy(country_name)
                if results:
                    return results[0].alpha_2
            except Exception:
                pass
        return country_name