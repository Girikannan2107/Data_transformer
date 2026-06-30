# server.py
import os
import io
import logging
import uuid
import json
import csv
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
    csv_path = os.path.join(UPLOAD_DIR, csv_filename) if csv_filename else None
    resume_path = os.path.join(UPLOAD_DIR, resume_filename) if resume_filename else None
    
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
        "logs": logs
    }

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
