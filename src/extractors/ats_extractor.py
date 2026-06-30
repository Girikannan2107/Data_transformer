# src/extractors/ats_extractor.py
import json
import logging
from src.extractors.base import BaseExtractor
from src.models import (
    InternalCandidateProfile, 
    Provenance, 
    LocationData, 
    LinksData,
    ExperienceData,
    EducationData
)
from src.models.domain_fields import (
    NameField, 
    EmailField, 
    PhoneField, 
    SkillField, 
    LocationField, 
    LinkField,
    HeadlineField,
    DomainField,
    ExperienceField,
    EducationField
)

logger = logging.getLogger(__name__)

class ATSExtractor(BaseExtractor):
    def extract(self, file_path: str, candidate_id: str) -> InternalCandidateProfile:
        profile = InternalCandidateProfile(candidate_id=candidate_id)
        
        base_prov = {
            "source": f"ATS:{file_path}",
            "method": "ATS_JSON_Parser",
            "confidence": 0.95  # Direct structured ATS export
        }
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            # Verify candidate_id
            extracted_id = data.get("candidate_id", data.get("id"))
            if extracted_id and str(extracted_id) != str(candidate_id):
                logger.warning(f"ATS candidate ID '{extracted_id}' does not match requested '{candidate_id}'. Returning empty profile.")
                return profile
                
            if name := data.get("full_name", data.get("name")):
                profile.full_name = NameField(raw_value=name.strip(), provenance=Provenance(field="full_name", **base_prov))
                
            if email := data.get("email"):
                profile.emails.append(EmailField(raw_value=email.strip(), provenance=Provenance(field="emails", **base_prov)))
                
            if phone := data.get("phone"):
                profile.phones.append(PhoneField(raw_value=phone.strip(), provenance=Provenance(field="phones", **base_prov)))
                
            if loc := data.get("location"):
                if isinstance(loc, dict):
                    loc_obj = LocationData(city=loc.get("city"), region=loc.get("region"), country=loc.get("country"))
                else:
                    loc_obj = LocationData(city=str(loc).strip())
                profile.location = LocationField(raw_value=loc_obj, provenance=Provenance(field="location", **base_prov))
                
            if headline := data.get("headline"):
                profile.headline = HeadlineField(raw_value=headline.strip(), provenance=Provenance(field="headline", **base_prov))
                
            if exp_years := data.get("experience_years"):
                profile.years_experience = DomainField(raw_value=float(exp_years), provenance=Provenance(field="years_experience", **base_prov))

            if skills := data.get("skills"):
                if isinstance(skills, list):
                    for skill in skills:
                        profile.skills.append(SkillField(raw_value=str(skill).strip(), provenance=Provenance(field="skills", **base_prov)))
                elif isinstance(skills, str):
                    for skill in skills.split("|"):
                        profile.skills.append(SkillField(raw_value=skill.strip(), provenance=Provenance(field="skills", **base_prov)))

            # Extract experience array
            if raw_exp := data.get("experience"):
                if isinstance(raw_exp, list):
                    for exp in raw_exp:
                        company = exp.get("company", "")
                        title = exp.get("title", "")
                        if company or title:
                            exp_data = ExperienceData(
                                company=company.strip() if company else "",
                                title=title.strip() if title else "",
                                start=exp.get("start"),
                                end=exp.get("end"),
                                summary=exp.get("summary")
                            )
                            profile.experience.append(ExperienceField(raw_value=exp_data, provenance=Provenance(field="experience", **base_prov)))

            # Extract education array
            if raw_edu := data.get("education"):
                if isinstance(raw_edu, list):
                    for edu in raw_edu:
                        inst = edu.get("institution", "")
                        if inst:
                            edu_data = EducationData(
                                institution=inst.strip(),
                                degree=edu.get("degree"),
                                field=edu.get("field"),
                                end_year=edu.get("end_year")
                            )
                            profile.education.append(EducationField(raw_value=edu_data, provenance=Provenance(field="education", **base_prov)))

        except FileNotFoundError:
            logger.error(f"ATS JSON file not found at {file_path}")
        except Exception as e:
            logger.error(f"Error parsing ATS JSON file {file_path}: {e}")
            
        return profile
