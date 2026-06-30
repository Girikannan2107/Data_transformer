import os
import requests
import logging
from typing import Optional, List, Dict
from src.extractors.base import BaseExtractor
from src.models import InternalCandidateProfile, TrackedField, Provenance, LocationData, LinksData

logger = logging.getLogger(__name__)

class GitHubExtractor(BaseExtractor):
    def __init__(self):
        self.token = os.getenv("GITHUB_TOKEN")
        self.headers = {"Accept": "application/vnd.github.v3+json"}
        if self.token:
            self.headers["Authorization"] = f"token {self.token}"

    def _fetch_realtime_skills(self, username: str, base_prov: dict) -> List[TrackedField]:
        skills = []
        try:
            repo_url = f"https://api.github.com/users/{username}/repos?type=owner&sort=updated&per_page=15"
            response = requests.get(repo_url, headers=self.headers, timeout=5.0)
            
            if response.status_code == 200:
                repos = response.json()
                languages_found = set()
                
                for repo in repos:
                    lang = repo.get("language")
                    if lang and lang not in languages_found:
                        languages_found.add(lang)
                        # Explicitly passing 'field="skills"' here
                        prov = Provenance(field="skills", **base_prov)
                        prov.confidence = 0.95 
                        prov.method = "REST_GET_Repo_Language_Inference"
                        skills.append(TrackedField(value=lang, provenance=prov))
                        
                logger.info(f"Real-time extraction found {len(skills)} skills for {username} from live repos.")
        except Exception as e:
            logger.warning(f"Failed to extract real-time repos for {username}: {e}")
            
        return skills

    def extract(self, profile_url: str, candidate_id: str) -> InternalCandidateProfile:
        profile = InternalCandidateProfile(candidate_id=candidate_id)
        
        base_prov = {
            "source": "GitHub_API_Live",
            "method": "REST_GET_Profile",
            "confidence": 0.85
        }

        try:
            username = profile_url.rstrip('/').split('/')[-1]
            if not username:
                raise ValueError("Invalid GitHub URL format")

            response = requests.get(f"https://api.github.com/users/{username}", headers=self.headers, timeout=5.0)
            
            if response.status_code == 403:
                logger.error("GitHub API Rate Limit exceeded.")
                return profile
            elif response.status_code != 200:
                return profile

            data = response.json()

            # Updated with 'field' parameter
            if data.get('name'):
                profile.full_name = TrackedField(value=data['name'], provenance=Provenance(field="full_name", **base_prov))
                
            if data.get('bio'):
                profile.headline = TrackedField(value=data['bio'], provenance=Provenance(field="headline", **base_prov))

            if data.get('location'):
                loc = LocationData(city=data['location'])
                profile.location = TrackedField(value=loc, provenance=Provenance(field="location", **base_prov))

            if data.get('html_url'):
                links = LinksData(github=data['html_url'])
                profile.links = TrackedField(value=links, provenance=Provenance(field="links", **base_prov))

            profile.skills = self._fetch_realtime_skills(username, base_prov)

        except Exception as e:
            logger.error(f"Robustness Guard: Failed to parse live GitHub profile {profile_url}: {e}")

        return profile