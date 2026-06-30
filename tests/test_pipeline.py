import pytest
from src.models import TrackedField, Provenance, InternalCandidateProfile
from src.normalizers.text_normalizer import Normalizer
from src.engine.merger import MergeEngine
from src.config import PipelineConfig
from src.engine.projection import ProjectionEngine
import json
import os

# --- 1. NORMALIZER TESTS ---
def test_normalize_email():
    prov = Provenance(source="test", method="test", confidence=1.0)
    field = TrackedField(value="  JOHN.DOE@EMAIL.COM  ", provenance=prov)
    result = Normalizer.normalize_email(field)
    assert result.value == "john.doe@email.com"
    assert result.provenance.normalization_applied == "Lowercase_Strip"

def test_normalize_phone_valid():
    prov = Provenance(source="test", method="test", confidence=0.8)
    field = TrackedField(value="(415) 555-2671", provenance=prov)
    result = Normalizer.normalize_phone(field, default_region="US")
    assert result.value == "+14155552671"
    assert result.provenance.confidence == 0.9 # Checks the +0.1 Validation Boost!

def test_normalize_skill_fuzzy():
    prov = Provenance(source="test", method="test", confidence=0.8)
    field = TrackedField(value="machine learnin", provenance=prov)
    result = Normalizer.normalize_skill(field)
    assert result.value == "Machine Learning" # RapidFuzz canonicalization

# --- 2. MERGE ENGINE TESTS ---
def test_merge_conflict_resolution():
    # Setup two conflicting names
    prov_high = Provenance(source="CSV", method="test", confidence=0.9)
    prov_low = Provenance(source="GitHub", method="test", confidence=0.8)
    
    p1 = InternalCandidateProfile(candidate_id="123")
    p1.full_name = TrackedField(value="John Doe", provenance=prov_high)
    
    p2 = InternalCandidateProfile(candidate_id="123")
    p2.full_name = TrackedField(value="Linus Torvalds", provenance=prov_low)
    
    # Merge should pick the one with higher confidence
    merged = MergeEngine.merge("123", [p1, p2])
    assert merged.full_name.value == "John Doe"

# --- 3. PROJECTION TESTS ---
def test_projection_missing_policy(tmp_path):
    # Create a temporary config file
    config_data = {
        "fields": [{"path": "location", "type": "string", "required": False}],
        "on_missing": "null"
    }
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(config_data))
    
    config = PipelineConfig(str(config_file))
    engine = ProjectionEngine(config)
    
    # Empty profile (location is None)
    profile = InternalCandidateProfile(candidate_id="123")
    result = engine.project(profile)
    
    # Missing value policy should insert null
    assert result["location"] is Noneimport pytest
from src.models import TrackedField, Provenance, InternalCandidateProfile
from src.normalizers.text_normalizer import Normalizer
from src.engine.merger import MergeEngine
from src.config import PipelineConfig
from src.engine.projection import ProjectionEngine
import json
import os

# --- 1. NORMALIZER TESTS ---
def test_normalize_email():
    prov = Provenance(source="test", method="test", confidence=1.0)
    field = TrackedField(value="  JOHN.DOE@EMAIL.COM  ", provenance=prov)
    result = Normalizer.normalize_email(field)
    assert result.value == "john.doe@email.com"
    assert result.provenance.normalization_applied == "Lowercase_Strip"

def test_normalize_phone_valid():
    prov = Provenance(source="test", method="test", confidence=0.8)
    field = TrackedField(value="(415) 555-2671", provenance=prov)
    result = Normalizer.normalize_phone(field, default_region="US")
    assert result.value == "+14155552671"
    assert result.provenance.confidence == 0.9 # Checks the +0.1 Validation Boost!

def test_normalize_skill_fuzzy():
    prov = Provenance(source="test", method="test", confidence=0.8)
    field = TrackedField(value="machine learnin", provenance=prov)
    result = Normalizer.normalize_skill(field)
    assert result.value == "Machine Learning" # RapidFuzz canonicalization

# --- 2. MERGE ENGINE TESTS ---
def test_merge_conflict_resolution():
    # Setup two conflicting names
    prov_high = Provenance(source="CSV", method="test", confidence=0.9)
    prov_low = Provenance(source="GitHub", method="test", confidence=0.8)
    
    p1 = InternalCandidateProfile(candidate_id="123")
    p1.full_name = TrackedField(value="John Doe", provenance=prov_high)
    
    p2 = InternalCandidateProfile(candidate_id="123")
    p2.full_name = TrackedField(value="Linus Torvalds", provenance=prov_low)
    
    # Merge should pick the one with higher confidence
    merged = MergeEngine.merge("123", [p1, p2])
    assert merged.full_name.value == "John Doe"

# --- 3. PROJECTION TESTS ---
def test_projection_missing_policy(tmp_path):
    # Create a temporary config file
    config_data = {
        "fields": [{"path": "location", "type": "string", "required": False}],
        "on_missing": "null"
    }
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(config_data))
    
    config = PipelineConfig(str(config_file))
    engine = ProjectionEngine(config)
    
    # Empty profile (location is None)
    profile = InternalCandidateProfile(candidate_id="123")
    result = engine.project(profile)
    
    # Missing value policy should insert null
    assert result["location"] is None