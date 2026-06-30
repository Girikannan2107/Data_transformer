# src/core/context.py
from dataclasses import dataclass, field
from typing import Dict, Any, List
import uuid
import time

@dataclass
class PipelineContext:
    pipeline_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    config: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)
    phase_history: List[str] = field(default_factory=list)
    current_candidate_id: str = ""
    start_time: float = field(default_factory=time.time)
    
    def set_phase(self, phase_name: str):
        self.phase_history.append(phase_name)
        
    def log_metric(self, key: str, value: Any):
        self.metrics[key] = value