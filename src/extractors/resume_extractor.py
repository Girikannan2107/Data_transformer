# src/extractors/resume_extractor.py
import re
import logging
from typing import List, Dict, Any, Optional
import spacy
from spacy.matcher import Matcher
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

# Lazy load spaCy model
_nlp = None
def get_nlp():
    global _nlp
    if _nlp is None:
        try:
            _nlp = spacy.load("en_core_web_sm")
        except Exception as e:
            logger.error(f"Failed to load spaCy model en_core_web_sm: {e}. Downloading it inline...")
            import subprocess
            subprocess.run(["python", "-m", "spacy", "download", "en_core_web_sm"], check=True)
            _nlp = spacy.load("en_core_web_sm")
    return _nlp

class ResumeExtractor(BaseExtractor):
    def __init__(self):
        # Massively expanded tech skill dictionary
        self.skill_keywords = [
            "python", "c++", "c", "java", "react", "javascript", "js", "typescript", "ts",
            "machine learning", "pytorch", "tensorflow", "sql", "aws", "docker", "kubernetes",
            "html", "css", "git", "api", "rest", "linux", "agile", "fastapi", "flask", "gemini",
            "langchain", "langgraph", "agentic ai", "multi-agent", "deep learning", "nlp"
        ]

    def _clean_spaced_out_text(self, text: str) -> str:
        clean_whitespace = re.sub(r'\s+', ' ', text).strip()
        words = [w for w in clean_whitespace.split(' ') if w]
        if not words:
            return text
            
        single_char_words = [w for w in words if len(w) == 1]
        if len(single_char_words) / len(words) > 0.70:
            logger.info("Spaced-out PDF text detected. Reconstructing...")
            normalized = re.sub(r' {2,}', '  ', text)
            normalized = normalized.replace('  ', ' _WORD_BOUND_ ')
            normalized = normalized.replace(' ', '')
            normalized = normalized.replace('_WORD_BOUND_', ' ')
            reconstructed = re.sub(r'\s+', ' ', normalized).strip()
            return reconstructed
        return text

    def _extract_text_from_docx(self, file_path: str) -> str:
        import zipfile
        from xml.etree import ElementTree
        text = ""
        try:
            with zipfile.ZipFile(file_path) as docx:
                xml_content = docx.read('word/document.xml')
                root = ElementTree.fromstring(xml_content)
                paragraphs = []
                for elem in root.iter():
                    if elem.tag.endswith('}t') and elem.text:
                        paragraphs.append(elem.text)
                text = "\n".join(paragraphs)
        except Exception as e:
            logger.error(f"Robustness Guard: Failed to read DOCX {file_path}: {e}")
        return text

    def _extract_text_from_pdf(self, file_path: str) -> str:
        text = ""
        try:
            import pdfplumber
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    extracted = page.extract_text()
                    if extracted:
                        text += extracted + "\n"
        except Exception as e:
            logger.error(f"pdfplumber extraction failed on {file_path}: {e}. Falling back to pypdf...")
            
        # Fallback to pypdf reader if pdfplumber fails
        if not text.strip():
            try:
                from pypdf import PdfReader
                reader = PdfReader(file_path)
                for page in reader.pages:
                    extracted = page.extract_text()
                    if extracted:
                        text += extracted + "\n"
            except Exception as e:
                logger.error(f"Fallback PyPDF extraction failed on {file_path}: {e}")
                
        # Tell us if the PDF is an unreadable image!
        if not text.strip():
            logger.warning(f"PDF {file_path} contained no readable text. It might be a scanned image.")
            
        return text

    def _segment_sections(self, text: str) -> Dict[str, str]:
        """
        Segment resume into sections using spaCy Matcher for headers.
        """
        nlp = get_nlp()
        doc = nlp(text)
        matcher = Matcher(nlp.vocab)
        
        # Define section header patterns
        matcher.add("SKILLS", [[{"LOWER": "skills"}], [{"LOWER": "technical"}, {"LOWER": "skills"}]])
        matcher.add("EXPERIENCE", [
            [{"LOWER": "experience"}], 
            [{"LOWER": "work"}, {"LOWER": "experience"}], 
            [{"LOWER": "professional"}, {"LOWER": "experience"}]
        ])
        matcher.add("EDUCATION", [[{"LOWER": "education"}], [{"LOWER": "academic"}, {"LOWER": "history"}]])
        matcher.add("PROJECTS", [[{"LOWER": "projects"}]])
        matcher.add("ACHIEVEMENTS", [[{"LOWER": "achievements"}], [{"LOWER": "awards"}]])
        matcher.add("CERTIFICATIONS", [[{"LOWER": "certifications"}], [{"LOWER": "licenses"}]])
        
        matches = matcher(doc)
        
        # Filter and sort matches by start token index
        matches = sorted(list(set(matches)), key=lambda x: x[1])
        
        sections = {}
        first_match_start = matches[0][1] if matches else len(doc)
        sections["header"] = doc[0:first_match_start].text
        
        for i in range(len(matches)):
            match_id, start, end = matches[i]
            label = nlp.vocab.strings[match_id].lower()
            
            # Find boundary for next section
            next_start = matches[i+1][1] if i + 1 < len(matches) else len(doc)
            sections[label] = doc[end:next_start].text
            
        return sections

    def extract(self, file_path: str, candidate_id: str) -> InternalCandidateProfile:
        profile = InternalCandidateProfile(candidate_id=candidate_id)
        
        is_docx = file_path.lower().endswith('.docx')
        source_type = "Resume_DOCX" if is_docx else "Resume_PDF"
        method_type = "spaCy_NLP_Extraction"
        
        base_prov = {
            "source": f"{source_type}:{file_path}",
            "method": method_type,
            "confidence": 0.8  # Elevated confidence for spaCy NLP parser
        }

        # 1. Read the text based on file format
        if is_docx:
            raw_text = self._extract_text_from_docx(file_path)
        else:
            raw_text = self._extract_text_from_pdf(file_path)
            
        if not raw_text:
            return profile
            
        # Reconstruct if text is spaced out
        raw_text = self._clean_spaced_out_text(raw_text)
        
        # Load spaCy NLP Pipeline
        nlp = get_nlp()
        doc = nlp(raw_text)
        
        # Segment resume sections
        sections = self._segment_sections(raw_text)

        # 2. Extract Name using NER (PERSON Entity)
        header_text = sections.get("header", "")
        name = None
        if header_text.strip():
            header_doc = nlp(header_text)
            persons = [ent.text for ent in header_doc.ents if ent.label_ == "PERSON"]
            if persons:
                name = persons[0].strip()
        
        if not name:
            # Fallback to the first line of the header
            lines = [l.strip() for l in header_text.split('\n') if l.strip()]
            if lines:
                name = lines[0]
                
        if name:
            profile.full_name = NameField(raw_value=name, provenance=Provenance(field="full_name", **base_prov))

        # 3. Extract Contacts (Email & Phone)
        emails = [token.text for token in doc if token.like_email]
        for email in emails:
            profile.emails.append(EmailField(raw_value=email, provenance=Provenance(field="emails", **base_prov)))

        # Phone matching
        phone_pattern = r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}|\+?\d{2}[-.\s]?\d{10}|\b\d{10}\b'
        phones = re.findall(phone_pattern, raw_text)
        for ph in phones:
            profile.phones.append(PhoneField(raw_value=ph.strip(), provenance=Provenance(field="phones", **base_prov)))

        # 4. Extract Social Links (LinkedIn, GitHub, LeetCode)
        linkedin_links = []
        github_links = []
        leetcode_links = []
        other_links = []
        
        # Parse urls using tokens and string checks
        for token in doc:
            t_text = token.text.strip().lower()
            if "linkedin.com" in t_text:
                linkedin_links.append(token.text.strip())
            elif "github.com" in t_text:
                github_links.append(token.text.strip())
            elif "leetcode.com" in t_text:
                leetcode_links.append(token.text.strip())

        # Build LinksData
        links_obj = LinksData(
            linkedin=linkedin_links[0] if linkedin_links else None,
            github=github_links[0] if github_links else None,
            portfolio=leetcode_links[0] if leetcode_links else None,
            other=other_links
        )
        if linkedin_links or github_links or leetcode_links:
            profile.links = LinkField(raw_value=links_obj, provenance=Provenance(field="links", **base_prov))

        # 5. Extract Headline and Location
        # Try to infer headline from the header section lines (skipping name and links)
        header_lines = [l.strip() for l in header_text.split('\n') if l.strip()]
        headline = None
        for hl in header_lines[1:]:
            if "@" not in hl and "com" not in hl and not re.search(phone_pattern, hl):
                headline = hl
                break
        if headline:
            profile.headline = HeadlineField(raw_value=headline, provenance=Provenance(field="headline", **base_prov))

        # Ingest Location using GPE
        location = None
        for ent in doc.ents:
            if ent.label_ == "GPE" and ent.start < 100:  # Geopolitical Entity near header
                location = ent.text
                break
        # Fallback GPE regex parse
        if not location:
            gpe_match = re.search(r'([A-Za-z\s]+),\s*([A-Za-z\s]+)\s*-\s*\d{6}', raw_text)
            if gpe_match:
                location = f"{gpe_match.group(1).strip()}, {gpe_match.group(2).strip()}"
                
        if location:
            parts = [p.strip() for p in location.split(',')]
            city = parts[0] if len(parts) > 0 else location
            region = parts[1] if len(parts) > 1 else None
            country = parts[2] if len(parts) > 2 else None
            loc_data = LocationData(city=city, region=region, country=country)
            profile.location = LocationField(raw_value=loc_data, provenance=Provenance(field="location", **base_prov))

        # 6. Extract Skills
        found_skills = []
        text_lower = raw_text.lower()
        for skill in self.skill_keywords:
            if re.search(rf'\b{re.escape(skill)}\b', text_lower):
                found_skills.append(SkillField(raw_value=skill, provenance=Provenance(field="skills", **base_prov)))
        profile.skills.extend(found_skills)

        # 7. Segment Experience Items
        exp_text = sections.get("experience", "")
        if exp_text.strip():
            # Segment experience blocks using line date ranges
            lines = [l.strip() for l in exp_text.split('\n') if l.strip()]
            current_block = []
            blocks = []
            
            # Helper pattern to check for years / date ranges
            date_range_pat = r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|January|February|March|April|June|July|August|September|October|November|December)\b.*\b(Present|20\d{2})\b'
            
            for line in lines:
                if re.search(date_range_pat, line, re.IGNORECASE):
                    if current_block:
                        blocks.append(current_block)
                        current_block = []
                current_block.append(line)
            if current_block:
                blocks.append(current_block)
                
            for block in blocks:
                if len(block) >= 1:
                    first_line = block[0]
                    # Parse company/title: split by | or -
                    parts = re.split(r'[-–|]', first_line)
                    company = parts[0].strip() if len(parts) > 0 else "Unknown Company"
                    title = parts[1].strip() if len(parts) > 1 else "Software Engineer"
                    
                    # Search for date range
                    date_match = re.search(date_range_pat, first_line, re.IGNORECASE)
                    if not date_match and len(block) > 1:
                        # Try second line
                        date_match = re.search(date_range_pat, block[1], re.IGNORECASE)
                        
                    start_date, end_date = None, None
                    if date_match:
                        date_parts = re.split(r'[-–]', date_match.group(0))
                        start_date = date_parts[0].strip() if len(date_parts) > 0 else None
                        end_date = date_parts[1].strip() if len(date_parts) > 1 else None
                        
                    exp_data = ExperienceData(
                        company=company,
                        title=title,
                        start=start_date,
                        end=end_date,
                        summary="\n".join(block[1:]) if len(block) > 1 else ""
                    )
                    profile.experience.append(ExperienceField(raw_value=exp_data, provenance=Provenance(field="experience", **base_prov)))

        # 8. Segment Education Items
        edu_text = sections.get("education", "")
        if edu_text.strip():
            lines = [l.strip() for l in edu_text.split('\n') if l.strip()]
            for line in lines:
                if any(word in line.lower() for word in ["college", "university", "school", "matric", "hsc"]):
                    parts = re.split(r'[-–|]', line)
                    inst = parts[0].strip()
                    degree = parts[1].strip() if len(parts) > 1 else None
                    
                    edu_data = EducationData(
                        institution=inst,
                        degree=degree,
                        field=None,
                        end_year=None
                    )
                    profile.education.append(EducationField(raw_value=edu_data, provenance=Provenance(field="education", **base_prov)))

        logger.info(f"spaCy NLP Extracted {len(profile.emails)} emails, {len(profile.phones)} phones, and {len(profile.skills)} skills from Resume.")
        return profile