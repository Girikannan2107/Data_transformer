# server.py
import os
import io
import logging
import uuid
import json
import csv
import shutil
from typing import Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from src.pipeline import CandidatePipeline

# Setup FastAPI App
app = FastAPI(title="Candidate Transformer Dashboard")

# Ensure upload directory exists
UPLOAD_DIR = os.path.join(os.getcwd(), "data", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Mount static folder
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    Accepts resume or CSV files, validates them, and saves them to a temp upload directory.
    """
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".pdf", ".docx", ".csv"]:
        raise HTTPException(status_code=400, detail="Invalid file type. Supported: .pdf, .docx, .csv")
    
    # Save file with a unique name to prevent collisions
    filename = f"{uuid.uuid4()}{ext}"
    file_path = os.path.join(UPLOAD_DIR, filename)
    
    try:
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")
        
    candidates = []
    num_rows = 0
    if ext == ".csv":
        try:
            text_stream = io.StringIO(content.decode("utf-8"))
            reader = csv.DictReader(text_stream)
            for row in reader:
                num_rows += 1
                cand_id = row.get("candidate_id")
                name = row.get("full_name")
                if cand_id:
                    candidates.append({"candidate_id": cand_id, "name": name or "Unknown Name"})
        except Exception as e:
            logging.getLogger("server").warning(f"Failed to parse CSV rows: {e}")

    return {
        "original_name": file.filename,
        "saved_filename": filename,
        "size_bytes": len(content),
        "validation_status": "Valid" if len(content) > 0 else "Invalid",
        "upload_time": uuid.uuid4().hex[:6],
        "candidates": candidates,
        "num_rows": num_rows
    }

@app.post("/api/run")
async def run_pipeline(
    candidate_id: str = Form("CAND-1001"),
    csv_filename: Optional[str] = Form(None),
    resume_filename: Optional[str] = Form(None),
    github_url: Optional[str] = Form(None)
):
    """
    Executes the 12-phase pipeline using uploaded files and returns the canonical profile, logs, and metrics.
    """
    # Create unique run directory
    run_id = f"run_{uuid.uuid4().hex[:8]}"
    run_dir = os.path.join(UPLOAD_DIR, "runs", run_id)
    os.makedirs(run_dir, exist_ok=True)
    
    csv_path = None
    if csv_filename:
        src = os.path.join(UPLOAD_DIR, csv_filename)
        dest = os.path.join(run_dir, "recruiter.csv")
        if os.path.exists(src):
            shutil.copy2(src, dest)
            csv_path = dest

    resume_path = None
    if resume_filename:
        src = os.path.join(UPLOAD_DIR, resume_filename)
        ext = os.path.splitext(resume_filename)[1].lower()
        dest = os.path.join(run_dir, f"resume{ext}")
        if os.path.exists(src):
            shutil.copy2(src, dest)
            resume_path = dest
            
    # Setup Log Capturer
    log_capture_string = io.StringIO()
    capture_handler = logging.StreamHandler(log_capture_string)
    capture_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    capture_handler.setFormatter(formatter)
    
    # Add handler to all package and framework loggers
    loggers_to_capture = [logging.getLogger("src"), logging.getLogger("CLI")]
    for logger in loggers_to_capture:
        logger.addHandler(capture_handler)
        
    try:
        pipeline = CandidatePipeline(config_path="data/output_schema.json")
        result = pipeline.run(
            candidate_id=candidate_id,
            csv_path=csv_path,
            github_url=github_url,
            resume_path=resume_path
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline execution crashed: {e}")
    finally:
        # Clean up handlers
        for logger in loggers_to_capture:
            logger.removeHandler(capture_handler)
            
    # Read captured logs
    logs = log_capture_string.getvalue().splitlines()
    
    return {
        "projected_profile": result.get("projected_profile"),
        "pipeline_report": result.get("pipeline_report"),
        "canonical_profile": result.get("canonical_profile"),
        "logs": logs
    }

class ProjectRequest(BaseModel):
    canonical_profile: dict
    schema_config: dict

class MockPipelineConfig:
    def __init__(self, schema_config: dict):
        self.fields = schema_config.get("fields", [])
        self.include_confidence = schema_config.get("include_confidence", True)
        self.include_provenance = schema_config.get("include_provenance", True)
        self.on_missing = schema_config.get("on_missing", "null")
        self.business_rules = schema_config.get("business_rules", {})
        # Normalization options
        self.phone_norm = schema_config.get("phone_norm", "E164")
        self.skills_norm = schema_config.get("skills_norm", "Canonical")
        self.country_norm = schema_config.get("country_norm", "ISO")
        self.dates_norm = schema_config.get("dates_norm", "YYYY-MM")

@app.post("/api/project")
async def project_only(req: ProjectRequest):
    """
    Runs ONLY the Projection Engine and Validation Engine on the provided canonical profile.
    No extraction, normalization, merging, or GitHub fetches are executed.
    """
    try:
        from src.models import InternalCandidateProfile
        from src.engine.projection import ProjectionEngine
        from src.engine.validator import ValidationEngine
        from src.core.context import PipelineContext
        
        # 1. Reconstruct profile model
        profile = InternalCandidateProfile.model_validate(req.canonical_profile)
        
        # 2. Reconstruct config from the provided schema_config dictionary
        config = MockPipelineConfig(req.schema_config)
        
        # 3. Run Projection
        projector = ProjectionEngine(config)
        projected_profile = projector.project(profile)
        
        # 4. Post-Process custom normalization choices
        if config.phone_norm == "Raw":
            if "phones" in projected_profile:
                raw_phones = []
                for p in profile.phones:
                    val = p.raw_value
                    if config.include_confidence or config.include_provenance:
                        item = {"value": val}
                        if config.include_confidence: item["confidence"] = p.provenance.confidence
                        if config.include_provenance: item["provenance"] = p.provenance.model_dump()
                        raw_phones.append(item)
                    else:
                        raw_phones.append(val)
                projected_profile["phones"] = raw_phones
                
        if config.skills_norm == "Original":
            if "skills" in projected_profile:
                raw_skills = []
                for s in profile.skills:
                    val = s.raw_value
                    if config.include_confidence or config.include_provenance:
                        item = {"value": val}
                        if config.include_confidence: item["confidence"] = s.provenance.confidence
                        if config.include_provenance: item["provenance"] = s.provenance.model_dump()
                        raw_skills.append(item)
                    else:
                        raw_skills.append(val)
                projected_profile["skills"] = raw_skills

        if config.country_norm == "Full":
            if "location" in projected_profile and projected_profile["location"]:
                mapping = {"US": "United States", "IN": "India", "CA": "Canada", "GB": "United Kingdom"}
                loc = projected_profile["location"]
                if isinstance(loc, dict) and "value" in loc and isinstance(loc["value"], dict):
                    c = loc["value"].get("country")
                    if c in mapping:
                        loc["value"]["country"] = mapping[c]
                elif isinstance(loc, dict) and loc.get("country"):
                    c = loc.get("country")
                    if c in mapping:
                        loc["country"] = mapping[c]
                        
        if config.dates_norm == "DD/MM/YYYY":
            if "experience" in projected_profile:
                for exp in projected_profile["experience"]:
                    target = exp if not (isinstance(exp, dict) and "value" in exp) else exp["value"]
                    if isinstance(target, dict):
                        for df in ["start", "end"]:
                            val = target.get(df)
                            if val and len(val) == 7 and "-" in val:
                                y, m = val.split("-")
                                target[df] = f"01/{m}/{y}"
            if "education" in projected_profile:
                for edu in projected_profile["education"]:
                    target = edu if not (isinstance(edu, dict) and "value" in edu) else edu["value"]
                    if isinstance(target, dict):
                        val = target.get("end_year")
                        if val and len(val) == 4:
                            target["end_year"] = f"01/01/{val}"
        
        # 5. Run Validation
        context = PipelineContext()
        validation_report = ValidationEngine.validate(projected_profile, config, context)
        
        return {
            "projected_profile": projected_profile,
            "validation_report": validation_report
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Projection failed: {e}")

@app.get("/")
async def get_index():
    """
    Serves the main SPA index page.
    """
    try:
        with open("static/index.html", "r", encoding="utf-8") as f:
            content = f.read()
        return HTMLResponse(content=content)
    except FileNotFoundError:
        return HTMLResponse(content="<h1>Dashboard file not found. Creating static/index.html next...</h1>")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
