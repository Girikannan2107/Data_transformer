import csv
import logging
from typing import Optional
from src.extractors.base import BaseExtractor
from src.models import InternalCandidateProfile, TrackedField, Provenance, ExperienceData

logger = logging.getLogger(__name__)

class CSVExtractor(BaseExtractor):
    def extract(self, file_path: str, candidate_id: str) -> InternalCandidateProfile:
        profile = InternalCandidateProfile(candidate_id=candidate_id)
        
        # Base metadata for this source
        base_prov = {
            "source": f"CSV:{file_path}",
            "method": "CSV_DictReader",
            "confidence": 0.9  # High confidence for structured HR data
        }

        try:
            with open(file_path, mode='r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                # For this assignment, we assume we are extracting the first row 
                # (Or the orchestrator feeds individual rows into this extractor)
                row = next(reader, None)
                
                if not row:
                    logger.warning(f"CSV file {file_path} is empty.")
                    return profile

                # Map Name
                if name := row.get('name', row.get('Name')):
                    profile.full_name = TrackedField(value=name.strip(), provenance=Provenance(**base_prov))
                
                # Map Email
                if email := row.get('email', row.get('Email')):
                    profile.emails.append(TrackedField(value=email.strip(), provenance=Provenance(**base_prov)))
                
                # Map Phone
                if phone := row.get('phone', row.get('Phone')):
                    profile.phones.append(TrackedField(value=phone.strip(), provenance=Provenance(**base_prov)))
                
                # Map Experience (Company + Title)
                company = row.get('current_company', row.get('Company'))
                title = row.get('title', row.get('Title'))
                if company or title:
                    exp = ExperienceData(
                        company=company.strip() if company else "Unknown",
                        title=title.strip() if title else "Unknown"
                    )
                    profile.experience.append(TrackedField(value=exp, provenance=Provenance(**base_prov)))
                    
        except FileNotFoundError:
            logger.error(f"Robustness Guard: Missing CSV file at {file_path}. Returning empty profile.")
        except Exception as e:
            logger.error(f"Robustness Guard: Corrupt CSV or read error in {file_path}: {e}")
            
        return profile