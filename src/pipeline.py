# src/pipeline.py
import os
import logging
import random
import time
from typing import Dict, Any, List, Optional
from src.core.context import PipelineContext
from src.config import PipelineConfig
from src.extractors.csv_extractor import CSVExtractor
from src.extractors.github_extractor import GitHubExtractor
from src.extractors.resume_extractor import ResumeExtractor
from src.extractors.ats_extractor import ATSExtractor
from src.normalizers.text_normalizer import Normalizer
from src.engine.merger import MergeEngine
from src.engine.projection import ProjectionEngine
from src.engine.confidence_engine import ConfidenceEngine
from src.engine.business_rules import BusinessRuleEngine
from src.engine.validator import ValidationEngine
from src.engine.entity_resolution import EntityResolutionGraph
from src.models import (
    InternalCandidateProfile, 
    RawCandidateRecord, 
    TrackedField,
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
import json

logger = logging.getLogger(__name__)

class CandidatePipeline:
    """
    12-Phase Multi-Source Candidate Data Transformation Pipeline.
    Supports dependency injection for all extractors, normalizers, and engines.
    """
    def __init__(
        self,
        config_path: str,
        csv_extractor: Optional[CSVExtractor] = None,
        github_extractor: Optional[GitHubExtractor] = None,
        resume_extractor: Optional[ResumeExtractor] = None,
        ats_extractor: Optional[ATSExtractor] = None,
        normalizer: Optional[Any] = None,
        merger: Optional[Any] = None,
        confidence_engine: Optional[Any] = None,
        business_rules: Optional[Any] = None,
        projection_engine: Optional[Any] = None,
        validator: Optional[Any] = None
    ):
        self.config = PipelineConfig(config_path)
        
        # Inject dependencies or use defaults
        self.csv_extractor = csv_extractor or CSVExtractor()
        self.github_extractor = github_extractor or GitHubExtractor()
        self.resume_extractor = resume_extractor or ResumeExtractor()
        self.ats_extractor = ats_extractor or ATSExtractor()
        self.normalizer = normalizer or Normalizer()
        self.merger = merger or MergeEngine()
        self.confidence_engine = confidence_engine or ConfidenceEngine()
        self.business_rules = business_rules or BusinessRuleEngine()
        self.projection_engine = projection_engine or ProjectionEngine(self.config)
        self.validator = validator or ValidationEngine()

    def _write_debug_json(self, filename: str, data: Any):
        debug_dir = os.path.join(os.getcwd(), "debug")
        os.makedirs(debug_dir, exist_ok=True)
        path = os.path.join(debug_dir, filename)
        try:
            if data is None:
                serialized = {}
            elif hasattr(data, "model_dump"):
                serialized = data.model_dump()
            elif isinstance(data, list):
                serialized = [item.model_dump() if hasattr(item, "model_dump") else item for item in data]
            else:
                serialized = data
                
            with open(path, "w", encoding="utf-8") as f:
                json.dump(serialized, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to write debug log {filename}: {e}")

    def run(
        self,
        candidate_id: str,
        csv_path: Optional[str] = None,
        github_url: Optional[str] = None,
        resume_path: Optional[str] = None,
        ats_path: Optional[str] = None
    ) -> Dict[str, Any]:
        
        # ----------------------------
        # PHASE 0: Bootstrap
        # ----------------------------
        context = PipelineContext(config=self.config._raw_config, current_candidate_id=candidate_id)
        context.set_phase("Phase 0: Bootstrap")
        logger.info(f"Initialized pipeline run {context.pipeline_id} for candidate {candidate_id}")

        # Initialize all 11 debug files to empty dictionary to guarantee they always exist on every run
        for i in range(1, 12):
            self._write_debug_json(f"{i:02d}_" + {
                1: "uploaded_resume.json", 2: "uploaded_csv.json", 3: "uploaded_github.json",
                4: "raw_resume.json", 5: "raw_csv.json", 6: "raw_github.json",
                7: "normalized.json", 8: "merged.json", 9: "projected.json",
                10: "final.json", 11: "pipeline_report.json"
            }[i], {})

        # Populate Uploaded Raw files
        if resume_path:
            try:
                if resume_path.lower().endswith('.docx'):
                    resume_text = self.resume_extractor._extract_text_from_docx(resume_path)
                else:
                    resume_text = self.resume_extractor._extract_text_from_pdf(resume_path)
                self._write_debug_json("01_uploaded_resume.json", {"raw_text": resume_text})
            except Exception:
                pass

        if csv_path:
            try:
                import csv
                with open(csv_path, mode='r', encoding='utf-8') as f:
                    csv_rows = list(csv.DictReader(f))
                self._write_debug_json("02_uploaded_csv.json", {"rows": csv_rows})
            except Exception:
                pass

        self._write_debug_json("03_uploaded_github.json", {"github_url": github_url})

        # ----------------------------
        # PHASE 1: Input Discovery
        # ----------------------------
        context.set_phase("Phase 1: Input Discovery")
        logger.info("Discovering and validating sources...")
        sources = []
        if csv_path:
            sources.append(("CSV", csv_path))
        if github_url:
            sources.append(("GitHub", github_url))
        if resume_path:
            sources.append(("PDF Resume", resume_path))
        if ats_path:
            sources.append(("ATS", ats_path))
            
        context.log_metric("discovered_sources_count", len(sources))
        context.log_metric("sources", [s[0] for s in sources])

        if not sources:
            logger.error("No valid sources discovered.")
            context.log_metric("pipeline_status", "FAILED")
            return {}

        # ----------------------------
        # PHASE 2: Extraction
        # ----------------------------
        context.set_phase("Phase 2: Extraction")
        logger.info("Extracting raw profiles...")
        
        raw_profiles = []
        resume_profile = None
        
        # 1. Extract Resume first (if available) to get details for auto-matching
        if resume_path:
            logger.info(f"Extracting from Resume first: {resume_path}")
            try:
                # Use a temp candidate ID initially, which will be updated post-auto-matching
                resume_profile = self.resume_extractor.extract(resume_path, "TEMP_ID")
                self._write_debug_json("04_raw_resume.json", resume_profile)
            except Exception as e:
                logger.error(f"Failed extraction from PDF Resume: {e}")
                
        # 2. Auto-match candidate_id from CSV using Resume email/name
        resolved_candidate_id = candidate_id
        if csv_path:
            try:
                import csv
                resume_emails = []
                resume_name = ""
                if resume_profile:
                    resume_emails = [e.raw_value.lower().strip() for e in resume_profile.emails if e and e.raw_value]
                    resume_name = resume_profile.full_name.raw_value.lower().strip() if resume_profile.full_name else ""
                
                matched_id = None
                first_id = None
                with open(csv_path, mode='r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        row_email = row.get("email", "").lower().strip()
                        row_name = row.get("full_name", "").lower().strip()
                        row_cand_id = row.get("candidate_id")
                        
                        if not first_id:
                            first_id = row_cand_id
                            
                        # Try to match
                        if (row_email and row_email in resume_emails) or (row_name and resume_name and (resume_name in row_name or row_name in resume_name)):
                            matched_id = row_cand_id
                            logger.info(f"Auto-match succeeded: Found Candidate {matched_id} in CSV matching Resume email/name.")
                            break
                            
                if matched_id:
                    resolved_candidate_id = matched_id
                elif first_id and (candidate_id == "CAND-1001" or not candidate_id):
                    # If we couldn't match but have a CSV, default candidate ID to the first row of CSV
                    resolved_candidate_id = first_id
                    logger.info(f"Auto-match failed. Defaulting to first candidate in CSV: {resolved_candidate_id}")
            except Exception as e:
                logger.warning(f"Auto-matching error: {e}")

        # Update the pipeline candidate_id context
        logger.info(f"Running pipeline under resolved Candidate ID: {resolved_candidate_id}")
        context.candidate_id = resolved_candidate_id
        
        # Update resume_profile candidate ID and provenance field values
        if resume_profile:
            resume_profile.candidate_id = resolved_candidate_id
            if resume_profile.full_name:
                resume_profile.full_name.provenance.field = "full_name"
            for email in resume_profile.emails:
                email.provenance.field = "emails"
            for phone in resume_profile.phones:
                phone.provenance.field = "phones"
            for skill in resume_profile.skills:
                skill.provenance.field = "skills"
            if resume_profile.location:
                resume_profile.location.provenance.field = "location"
            if resume_profile.links:
                resume_profile.links.provenance.field = "links"
            if resume_profile.headline:
                resume_profile.headline.provenance.field = "headline"
            for exp in resume_profile.experience:
                exp.provenance.field = "experience"
            for edu in resume_profile.education:
                edu.provenance.field = "education"
                
            raw_profiles.append(resume_profile)
            
        # 3. Extract other active sources using the final resolved candidate_id
        other_sources = [s for s in sources if s[0] != "PDF Resume"]
        random.shuffle(other_sources)
        
        for source_type, identifier in other_sources:
            logger.info(f"Extracting from: {source_type} ({identifier})")
            try:
                if source_type == "CSV":
                    profile = self.csv_extractor.extract(identifier, resolved_candidate_id)
                    self._write_debug_json("05_raw_csv.json", profile)
                elif source_type == "GitHub":
                    profile = self.github_extractor.extract(identifier, resolved_candidate_id)
                    self._write_debug_json("06_raw_github.json", profile)
                    self._write_debug_json("03_uploaded_github.json", self.github_extractor.last_raw_api_data or {"github_url": identifier})
                elif source_type == "ATS":
                    profile = self.ats_extractor.extract(identifier, resolved_candidate_id)
                
                raw_profiles.append(profile)
            except Exception as e:
                logger.error(f"Failed extraction from {source_type}: {e}")

        # Check if we should dynamically run GitHub extractor from Resume links
        has_github_in_sources = any(s[0] == "GitHub" for s in sources)
        if not has_github_in_sources and resume_profile and resume_profile.links and resume_profile.links.raw_value.github:
            inferred_git_url = resume_profile.links.raw_value.github
            logger.info(f"Dynamically discovered GitHub profile in Resume links: {inferred_git_url}")
            try:
                profile = self.github_extractor.extract(inferred_git_url, resolved_candidate_id)
                raw_profiles.append(profile)
                self._write_debug_json("06_raw_github.json", profile)
                self._write_debug_json("03_uploaded_github.json", self.github_extractor.last_raw_api_data or {"github_url": inferred_git_url})
            except Exception as e:
                logger.error(f"Failed dynamic GitHub extraction: {e}")

        if not raw_profiles:
            logger.error("No raw data was successfully extracted.")
            context.log_metric("pipeline_status", "FAILED")
            return {}

        # ----------------------------
        # PHASE 3: Field Classification
        # ----------------------------
        context.set_phase("Phase 3: Field Classification")
        logger.info("Classifying primitives into structured domain fields...")
        
        classified_profiles = []
        for raw_profile in raw_profiles:
            classified = InternalCandidateProfile(candidate_id=resolved_candidate_id)
            
            # Map scalars
            if raw_profile.full_name:
                classified.full_name = NameField(
                    raw_value=raw_profile.full_name.raw_value,
                    canonical_value=raw_profile.full_name.canonical_value,
                    provenance=raw_profile.full_name.provenance
                )
            if raw_profile.location:
                classified.location = LocationField(
                    raw_value=raw_profile.location.raw_value,
                    canonical_value=raw_profile.location.canonical_value,
                    provenance=raw_profile.location.provenance
                )
            if raw_profile.links:
                classified.links = LinkField(
                    raw_value=raw_profile.links.raw_value,
                    canonical_value=raw_profile.links.canonical_value,
                    provenance=raw_profile.links.provenance
                )
            if raw_profile.headline:
                classified.headline = HeadlineField(
                    raw_value=raw_profile.headline.raw_value,
                    canonical_value=raw_profile.headline.canonical_value,
                    provenance=raw_profile.headline.provenance
                )
            if raw_profile.years_experience:
                classified.years_experience = DomainField(
                    raw_value=raw_profile.years_experience.raw_value,
                    canonical_value=raw_profile.years_experience.canonical_value,
                    provenance=raw_profile.years_experience.provenance
                )
                
            # Map arrays
            classified.emails = [EmailField(raw_value=e.raw_value, canonical_value=e.canonical_value, provenance=e.provenance) for e in raw_profile.emails]
            classified.phones = [PhoneField(raw_value=p.raw_value, canonical_value=p.canonical_value, provenance=p.provenance) for p in raw_profile.phones]
            classified.skills = [SkillField(raw_value=s.raw_value, canonical_value=s.canonical_value, provenance=s.provenance) for s in raw_profile.skills]
            classified.experience = [ExperienceField(raw_value=exp.raw_value, canonical_value=exp.canonical_value, provenance=exp.provenance) for exp in raw_profile.experience]
            classified.education = [EducationField(raw_value=edu.raw_value, canonical_value=edu.canonical_value, provenance=edu.provenance) for edu in raw_profile.education]
            
            classified_profiles.append(classified)

        # ----------------------------
        # PHASE 3.5: Generate Extraction Report
        # ----------------------------
        extraction_report = {}
        for idx, rp in enumerate(classified_profiles):
            src_name = "Unknown_Source"
            if rp.full_name:
                src_name = rp.full_name.provenance.source
            elif rp.emails:
                src_name = rp.emails[0].provenance.source
            elif rp.skills:
                src_name = rp.skills[0].provenance.source
                
            extraction_report[src_name] = {}
            if rp.full_name:
                extraction_report[src_name]["full_name"] = str(rp.full_name.raw_value)
            if rp.emails:
                extraction_report[src_name]["emails"] = [str(e.raw_value) for e in rp.emails]
            if rp.phones:
                extraction_report[src_name]["phones"] = [str(ph.raw_value) for ph in rp.phones]
            if rp.location:
                loc = rp.location.raw_value
                extraction_report[src_name]["location"] = f"{loc.city}, {loc.region}, {loc.country}" if hasattr(loc, "city") else str(loc)
            if rp.links:
                lk = rp.links.raw_value
                extraction_report[src_name]["links"] = f"github: {lk.github}" if hasattr(lk, "github") else str(lk)
            if rp.headline:
                extraction_report[src_name]["headline"] = str(rp.headline.raw_value)
            if rp.years_experience:
                extraction_report[src_name]["years_experience"] = str(rp.years_experience.raw_value)
            if rp.skills:
                extraction_report[src_name]["skills"] = [str(s.raw_value) for s in rp.skills]
            if rp.experience:
                extraction_report[src_name]["experience"] = [f"{exp.raw_value.company} - {exp.raw_value.title}" for exp in rp.experience]
            if rp.education:
                extraction_report[src_name]["education"] = [f"{edu.raw_value.institution}" for edu in rp.education]

        logger.info(f"🏆 RAW EXTRACTION REPORT (BEFORE NORMALIZATION/MERGING) 🏆:\n{json.dumps(extraction_report, indent=2)}")
        context.log_metric("extraction_report", extraction_report)

        # ----------------------------
        # PHASE 4: Normalization
        # ----------------------------
        context.set_phase("Phase 4: Normalization")
        logger.info("Applying deterministic normalization rules...")
        
        for p in classified_profiles:
            if p.full_name: p.full_name = self.normalizer.normalize_name(p.full_name)
            if p.headline: p.headline = self.normalizer.normalize_name(p.headline)
            
            p.emails = [self.normalizer.normalize_email(e) for e in p.emails if e]
            p.phones = [self.normalizer.normalize_phone(p_num) for p_num in p.phones if p_num]
            p.skills = [self.normalizer.normalize_skill(s) for s in p.skills if s]
            p.experience = [self.normalizer.normalize_experience(exp) for exp in p.experience if exp]
            p.education = [self.normalizer.normalize_education(edu) for edu in p.education if edu]

        self._write_debug_json("07_normalized.json", classified_profiles)

        # ----------------------------
        # PHASE 5: Entity Resolution
        # ----------------------------
        context.set_phase("Phase 5: Entity Resolution")
        logger.info("Running entity resolution clusters (Exact & RapidFuzz)...")
        # Entity resolution groupings are processed during merge.

        # ----------------------------
        # PHASE 6: Merge Engine
        # ----------------------------
        context.set_phase("Phase 6: Merge Engine")
        logger.info("Executing weighted aggregation and evidence merge...")
        canonical_profile = self.merger.merge(resolved_candidate_id, classified_profiles)

        # ----------------------------
        # PHASE 7: Confidence Engine
        # ----------------------------
        context.set_phase("Phase 7: Confidence Engine")
        logger.info("Calculating confidence evolution...")
        canonical_profile = self.confidence_engine.evaluate(canonical_profile)
        self._write_debug_json("08_merged.json", canonical_profile)

        # ----------------------------
        # PHASE 8: Provenance Engine
        # ----------------------------
        context.set_phase("Phase 8: Provenance Engine")
        logger.info("Finalizing field-level provenance records...")

        # ----------------------------
        # PHASE 9: Business Rules
        # ----------------------------
        context.set_phase("Phase 9: Business Rules")
        logger.info("Applying business validation policies...")
        canonical_profile = self.business_rules.apply(canonical_profile, context)

        # ----------------------------
        # PHASE 10: Projection Engine
        # ----------------------------
        context.set_phase("Phase 10: Projection Engine")
        logger.info("Projecting to custom template...")
        projected_profile = self.projection_engine.project(canonical_profile)
        self._write_debug_json("09_projected.json", projected_profile)

        # ----------------------------
        # PHASE 11: Validation
        # ----------------------------
        context.set_phase("Phase 11: Validation")
        logger.info("Validating schema outputs...")
        validation_report = self.validator.validate(projected_profile, self.config, context)
        self._write_debug_json("10_final.json", {"is_valid": validation_report["is_valid"], "profile": projected_profile})

        # ----------------------------
        # PHASE 12: Serialization
        # ----------------------------
        context.set_phase("Phase 12: Serialization")
        logger.info("Serializing and writing statistics reports...")
        
        execution_time_ms = int((time.time() - context.start_time) * 1000)
        context.log_metric("execution_time_ms", execution_time_ms)
        context.log_metric("pipeline_status", "SUCCESS")
        
        pipeline_report = {
            "pipeline_id": context.pipeline_id,
            "candidate_id": resolved_candidate_id,
            "execution_time_ms": execution_time_ms,
            "metrics": context.metrics,
            "phase_history": context.phase_history,
            "validation_report": validation_report
        }
        self._write_debug_json("11_pipeline_report.json", pipeline_report)
        
        logger.info(f"Pipeline executed successfully in {execution_time_ms} ms.")

        return {
            "canonical_profile": canonical_profile.model_dump(),
            "projected_profile": projected_profile,
            "validation_report": validation_report,
            "pipeline_report": pipeline_report
        }