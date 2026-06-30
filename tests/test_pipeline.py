import pytest
import json
import os
from typing import List
from src.models import (
    InternalCandidateProfile, 
    TrackedField, 
    Provenance, 
    LocationData, 
    ExperienceData, 
    EducationData,
    NameField,
    EmailField,
    PhoneField,
    SkillField,
    LocationField,
    LinkField,
    ExperienceField,
    EducationField
)
from src.normalizers.text_normalizer import Normalizer
from src.engine.entity_resolution import EntityResolutionGraph
from src.engine.merger import MergeEngine
from src.engine.confidence_engine import ConfidenceEngine
from src.engine.business_rules import BusinessRuleEngine
from src.engine.projection import ProjectionEngine
from src.engine.validator import ValidationEngine
from src.config import PipelineConfig
from src.core.context import PipelineContext
from src.pipeline import CandidatePipeline

# =====================================================================
# 1. NORMALIZER TESTS
# =====================================================================

def test_normalize_email():
    prov = Provenance(source="test", method="test", confidence=1.0)
    field = EmailField(raw_value="  JOHN.DOE@EMAIL.COM  ", provenance=prov)
    result = Normalizer.normalize_email(field)
    assert result.value == "john.doe@email.com"
    assert "Lowercase_Strip" in result.provenance.normalization_applied
    # Check that confidence remains unmodified
    assert result.provenance.confidence == 1.0

def test_normalize_phone():
    prov = Provenance(source="test", method="test", confidence=0.8)
    field = PhoneField(raw_value="(415) 555-2671", provenance=prov)
    result = Normalizer.normalize_phone(field)
    assert result.value == "+14155552671"
    assert "E164_Format" in result.provenance.normalization_applied
    # Check that confidence remains unmodified in Normalizer
    assert result.provenance.confidence == 0.8

def test_normalize_skill_fuzzy():
    prov = Provenance(source="test", method="test", confidence=0.8)
    field = SkillField(raw_value="machine learnin", provenance=prov)
    result = Normalizer.normalize_skill(field)
    assert result.value == "Machine Learning"
    assert any("Fuzzy_Match" in n for n in result.provenance.normalization_applied)

# =====================================================================
# 2. ENTITY RESOLUTION TESTS
# =====================================================================

def test_entity_resolution_exact():
    prov1 = Provenance(source="S1", method="m", confidence=0.8)
    prov2 = Provenance(source="S2", method="m", confidence=0.7)
    
    e1 = EmailField(raw_value="john@email.com", provenance=prov1)
    e2 = EmailField(raw_value="JOHN@email.com ", provenance=prov2)
    e3 = EmailField(raw_value="different@email.com", provenance=prov2)
    
    clusters = EntityResolutionGraph.group_array_fields([e1, e2, e3], "emails")
    assert len(clusters) == 2
    assert len(clusters[0]) == 2
    assert len(clusters[1]) == 1

def test_entity_resolution_fuzzy_skills():
    prov = Provenance(source="S1", method="m", confidence=0.8)
    s1 = SkillField(raw_value="Python", provenance=prov)
    s2 = SkillField(raw_value="python", provenance=prov)
    s3 = SkillField(raw_value="Java", provenance=prov)
    
    clusters = EntityResolutionGraph.group_array_fields([s1, s2, s3], "skills")
    assert len(clusters) == 2

# =====================================================================
# 3. MERGE ENGINE TESTS
# =====================================================================

def test_merge_weighted_aggregation():
    prov_high = Provenance(source="CSV", method="reader", confidence=0.9)
    prov_low = Provenance(source="GitHub", method="api", confidence=0.8)
    
    p1 = InternalCandidateProfile(candidate_id="123")
    p1.full_name = NameField(raw_value="John Doe", provenance=prov_high)
    
    p2 = InternalCandidateProfile(candidate_id="123")
    p2.full_name = NameField(raw_value="Linus Torvalds", provenance=prov_low)
    
    merged = MergeEngine.merge("123", [p1, p2])
    assert merged.full_name.value == "John Doe"
    assert len(merged.full_name.provenance.rejected_sources) == 1
    assert merged.full_name.provenance.rejected_sources[0]["value"] == "Linus Torvalds"
    assert merged.full_name.provenance.agreement_count == 1

# =====================================================================
# 4. CONFIDENCE ENGINE TESTS
# =====================================================================

def test_confidence_calculations():
    prov1 = Provenance(source="CSV", method="m", confidence=0.8)
    prov2 = Provenance(source="GitHub", method="m", confidence=0.8)
    
    p1 = InternalCandidateProfile(candidate_id="123")
    p1.emails = [EmailField(raw_value="john@email.com", provenance=prov1)]
    
    p2 = InternalCandidateProfile(candidate_id="123")
    p2.emails = [EmailField(raw_value="john@email.com", provenance=prov2)]
    
    merged = MergeEngine.merge("123", [p1, p2])
    # Agreement count should be 2
    assert merged.emails[0].provenance.agreement_count == 2
    
    # Calculate confidence
    evaluated = ConfidenceEngine.evaluate(merged)
    # Base confidence 0.8 + 0.05 agreement bonus + 0.05 email format validation bonus = 0.90
    assert evaluated.emails[0].confidence == 0.90
    assert "Agreement Bonus: +0.05" in "".join(evaluated.emails[0].provenance.confidence_evolution)

# =====================================================================
# 5. PROJECTION ENGINE TESTS
# =====================================================================

def test_projection_nested_paths(tmp_path):
    config_data = {
        "fields": [
            {"path": "candidate_id", "type": "string", "required": True},
            {"path": "city_name", "from": "location.city", "type": "string"}
        ],
        "include_confidence": False,
        "include_provenance": False,
        "on_missing": "null"
    }
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(config_data))
    
    config = PipelineConfig(str(config_file))
    engine = ProjectionEngine(config)
    
    prov = Provenance(source="S", method="m", confidence=0.9)
    profile = InternalCandidateProfile(candidate_id="123")
    profile.location = LocationField(
        raw_value=LocationData(city="Coimbatore"),
        canonical_value=LocationData(city="Coimbatore"),
        provenance=prov
    )
    
    projected = engine.project(profile)
    assert projected["candidate_id"] == "123"
    assert projected["city_name"] == "Coimbatore"

# =====================================================================
# 6. VALIDATOR ENGINE TESTS
# =====================================================================

def test_validation_engine():
    context = PipelineContext()
    config_def = {
        "fields": [
            {"path": "primary_email", "type": "string", "required": True}
        ],
        "on_missing": "null"
    }
    
    # Valid Case
    payload = {"primary_email": "john@email.com"}
    report = ValidationEngine.validate(payload, config_def, context)
    assert report["is_valid"] is True
    
    # Invalid Email Case
    payload = {"primary_email": "invalid-email-string"}
    report = ValidationEngine.validate(payload, config_def, context)
    assert report["is_valid"] is False
    assert len(report["errors"]) > 0

# =====================================================================
# 7. END-TO-END PIPELINE RUN TEST
# =====================================================================

def test_pipeline_e2e(tmp_path):
    # Set up config file
    config_data = {
        "fields": [
            {"path": "candidate_id", "type": "string", "required": True},
            {"path": "full_name", "type": "string", "required": True},
            {"path": "primary_email", "from": "emails[0]", "type": "string"}
        ],
        "include_confidence": True,
        "include_provenance": True,
        "on_missing": "null",
        "business_rules": {
            "min_field_confidence": 0.40,
            "required_fields": ["full_name"]
        }
    }
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(config_data))
    
    # Set up pipeline
    pipeline = CandidatePipeline(str(config_file))
    
    # Run with CSV path (using our test CSV in data/)
    csv_test_path = "data/recruiter_data.csv"
    if os.path.exists(csv_test_path):
        result = pipeline.run(candidate_id="CAND-8832", csv_path=csv_test_path)
        assert "projected_profile" in result
        assert result["projected_profile"]["candidate_id"] == "CAND-8832"
        assert "full_name" in result["projected_profile"]