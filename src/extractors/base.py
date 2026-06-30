from abc import ABC, abstractmethod
from typing import Optional
from src.models import InternalCandidateProfile

class BaseExtractor(ABC):
    """
    Abstract base class for all data extractors.
    Enforces the contract that all inputs must yield a standard InternalCandidateProfile.
    """
    
    @abstractmethod
    def extract(self, source_identifier: str, candidate_id: str) -> InternalCandidateProfile:
        """
        Extracts data from the source and maps it to the internal schema.
        :param source_identifier: File path, URL, or JSON string.
        :param candidate_id: A unique ID to link this partial profile to a candidate.
        """
        pass