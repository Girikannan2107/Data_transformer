# src/extractors/csv_extractor.py
import csv
import logging
from typing import Optional
from src.extractors.base import BaseExtractor
from src.models import (
    InternalCandidateProfile, 
    TrackedField, 
    Provenance, 
    ExperienceData, 
    LocationData,
    LinksData
)

logger = logging.getLogger(__name__)

class CSVExtractor(BaseExtractor):
    def extract(self, file_path: str, candidate_id: str) -> InternalCandidateProfile:
        profile = InternalCandidateProfile(candidate_id=candidate_id)
        
        base_prov = {
            "source": f"CSV:{file_path}",
            "method": "CSV_DictReader",
            "confidence": 0.9  # Structured recruiter CSV export
        }

        try:
            with open(file_path, mode='r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                
                # Match the row containing requested candidate_id
                matched_row = None
                for row in reader:
                    if row.get("candidate_id") == candidate_id:
                        matched_row = row
                        break
                        
                if not matched_row:
                    logger.warning(f"Candidate '{candidate_id}' not found in CSV file at {file_path}.")
                    return profile

                # Map Name
                if name := matched_row.get('full_name'):
                    profile.full_name = TrackedField(value=name.strip(), provenance=Provenance(field="full_name", **base_prov))
                
                # Map Email
                if email := matched_row.get('email'):
                    profile.emails.append(TrackedField(value=email.strip(), provenance=Provenance(field="emails", **base_prov)))
                
                # Map Phone
                if phone := matched_row.get('phone'):
                    profile.phones.append(TrackedField(value=phone.strip(), provenance=Provenance(field="phones", **base_prov)))
                
                # Map Location
                if loc_str := matched_row.get('location'):
                    parts = [p.strip() for p in loc_str.split(',')]
                    city, region, country = None, None, None
                    if len(parts) >= 3:
                        city, region, country = parts[0], parts[1], parts[2]
                    elif len(parts) == 2:
                        city, country = parts[0], parts[1]
                    elif len(parts) == 1:
                        city = parts[0]
                    loc_data = LocationData(city=city, region=region, country=country)
                    profile.location = TrackedField(value=loc_data, provenance=Provenance(field="location", **base_prov))

                # Map Links (GitHub)
                if github := matched_row.get('github'):
                    links_data = LinksData(github=github.strip())
                    profile.links = TrackedField(value=links_data, provenance=Provenance(field="links", **base_prov))

                # Map Headline
                if headline := matched_row.get('headline'):
                    profile.headline = TrackedField(value=headline.strip(), provenance=Provenance(field="headline", **base_prov))

                # Map Skills
                if skills_str := matched_row.get('skills'):
                    for s in skills_str.split('|'):
                        profile.skills.append(TrackedField(value=s.strip(), provenance=Provenance(field="skills", **base_prov)))

                # Map Experience Years
                if exp_years := matched_row.get('experience_years'):
                    try:
                        profile.years_experience = TrackedField(value=float(exp_years), provenance=Provenance(field="years_experience", **base_prov))
                    except ValueError:
                        pass

                # Map Experience (Company + Title)
                company = matched_row.get('company')
                title = matched_row.get('job_title')
                if company or title:
                    exp = ExperienceData(
                        company=company.strip() if company else "",
                        title=title.strip() if title else ""
                    )
                    profile.experience.append(TrackedField(value=exp, provenance=Provenance(field="experience", **base_prov)))
                    
        except FileNotFoundError:
            logger.error(f"Missing CSV file at {file_path}.")
        except Exception as e:
            logger.error(f"Error reading CSV {file_path}: {e}")
            
        return profile