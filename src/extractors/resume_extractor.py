import re
import logging
from pypdf import PdfReader
from typing import List
from src.extractors.base import BaseExtractor
from src.models import InternalCandidateProfile, TrackedField, Provenance

logger = logging.getLogger(__name__)

class ResumeExtractor(BaseExtractor):
    def __init__(self):
        # Massively expanded tech skill dictionary
        self.skill_keywords = [
            "python", "c++", "c", "java", "react", "javascript", "js", "typescript", "ts",
            "machine learning", "pytorch", "tensorflow", "sql", "aws", "docker", "kubernetes",
            "html", "css", "git", "api", "rest", "linux", "agile", "fastapi", "flask", "gemini"
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
                text = " ".join(paragraphs)
        except Exception as e:
            logger.error(f"Robustness Guard: Failed to read DOCX {file_path}: {e}")
        return text

    def _extract_text_from_pdf(self, file_path: str) -> str:
        text = ""
        try:
            reader = PdfReader(file_path)
            for page in reader.pages:
                extracted = page.extract_text()
                if extracted:
                    text += extracted + " "
        except Exception as e:
            logger.error(f"Robustness Guard: Failed to read PDF {file_path}: {e}")
        
        # Tell us if the PDF is an unreadable image!
        if not text.strip():
            logger.warning(f"PDF {file_path} contained no readable text. It might be a scanned image.")
            
        return text

    def extract(self, file_path: str, candidate_id: str) -> InternalCandidateProfile:
        profile = InternalCandidateProfile(candidate_id=candidate_id)
        
        is_docx = file_path.lower().endswith('.docx')
        source_type = "Resume_DOCX" if is_docx else "Resume_PDF"
        method_type = "DOCX_XML_Extraction" if is_docx else "PyPDF_Regex_Extraction"
        
        base_prov = {
            "source": f"{source_type}:{file_path}",
            "method": method_type,
            "confidence": 0.7  # Lower confidence due to unstructured text parsing
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

        # 2. Extract Email using Regex
        email_pattern = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
        emails_found = re.findall(email_pattern, raw_text)
        if emails_found:
            profile.emails.append(TrackedField(value=emails_found[0], provenance=Provenance(**base_prov)))

        # 3. Extract Phone using Regex
        phone_pattern = r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}'
        phones_found = re.findall(phone_pattern, raw_text)
        if phones_found:
            profile.phones.append(TrackedField(value=phones_found[0], provenance=Provenance(**base_prov)))

        # 4. Extract Skills using Keyword Token Matching
        text_lower = raw_text.lower()
        found_skills = []
        for skill in self.skill_keywords:
            if re.search(rf'\b{re.escape(skill)}\b', text_lower):
                found_skills.append(TrackedField(value=skill, provenance=Provenance(**base_prov)))
        
        profile.skills.extend(found_skills)

        logger.info(f"Extracted {len(emails_found)} emails, {len(phones_found)} phones, and {len(found_skills)} skills from PDF.")
        return profile