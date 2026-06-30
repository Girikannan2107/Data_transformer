import logging
import random
from typing import Dict, Any, List, Callable
from src.config import PipelineConfig
from src.extractors.csv_extractor import CSVExtractor
from src.extractors.github_extractor import GitHubExtractor
from src.extractors.resume_extractor import ResumeExtractor
from src.normalizers.text_normalizer import Normalizer
from src.engine.merger import MergeEngine
from src.engine.projection import ProjectionEngine

logger = logging.getLogger(__name__)

class CandidatePipeline:
    def __init__(self, config_path: str):
        self.config = PipelineConfig(config_path)
        self.csv_extractor = CSVExtractor()
        self.github_extractor = GitHubExtractor()
        self.resume_extractor = ResumeExtractor()
        self.projection_engine = ProjectionEngine(self.config)

    def run(self, candidate_id: str, csv_path: str = None, github_url: str = None, resume_path: str = None) -> Dict[str, Any]:
        
        # 1. Register available tasks
        # We store them as a list of tuples: (source_name, extraction_function)
        tasks = []
        if csv_path:
            tasks.append(("CSV", lambda: self.csv_extractor.extract(csv_path, candidate_id)))
        if github_url:
            tasks.append(("GitHub", lambda: self.github_extractor.extract(github_url, candidate_id)))
        if resume_path:
            tasks.append(("PDF Resume", lambda: self.resume_extractor.extract(resume_path, candidate_id)))

        # 2. Randomize extraction order (Source-Agnostic)
        random.shuffle(tasks)
        
        profiles = []
        logger.info(f"Starting extraction for {candidate_id} across {len(tasks)} sources in randomized order.")
        
        for name, extract_func in tasks:
            logger.info(f"Extracting from: {name}")
            try:
                profiles.append(extract_func())
            except Exception as e:
                logger.error(f"Failed extraction for source {name}: {e}")

        if not profiles:
            logger.error("No valid input sources collected.")
            return {}

        # 3. Normalization (Unchanged)
        logger.info("Applying deterministic normalization rules...")
        for p in profiles:
            p.full_name = Normalizer.normalize_name(p.full_name)
            p.headline = Normalizer.normalize_name(p.headline)
            p.emails = [Normalizer.normalize_email(e) for e in p.emails if e]
            p.phones = [Normalizer.normalize_phone(p_num) for p_num in p.phones if p_num]
            p.skills = [Normalizer.normalize_skill(s) for s in p.skills if s]

        # 4. Merge Engine (Deterministic)
        logger.info("Merging profiles & applying conflict resolution...")
        canonical_profile = MergeEngine.merge(candidate_id, profiles)

        # 5. Projection Engine (Configurable)
        logger.info("Projecting to final JSON schema via runtime configuration...")
        return self.projection_engine.project(canonical_profile)