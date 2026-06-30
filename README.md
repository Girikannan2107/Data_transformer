# Candidate Data Transformer

Candidate Data Transformer is an industrial-grade, AI-powered Candidate Data Ingestion and Transformation Platform. It is designed to extract, normalize, resolve, and merge candidate profiles from multiple structured and unstructured sources (Resumes in PDF/DOCX, Recruiter CSV exports, and Live GitHub Profiles) into a single, unified canonical JSON profile.

The application follows the official Stage 2 project guidelines, presenting a professional, responsive, glassmorphic Applicant Tracking System (ATS) interface built with Vanilla JS and CSS, backed by a FastAPI/Python backend.

---

## 🚀 Key Platform Features

1. **Multi-Source Extraction**: Parses contact details, experience, education, and skills from unstructured resumes (PDF/DOCX), structured database rows (CSV), and live API connections (GitHub Profile & Repositories).
2. **Absolute Request Isolation**: Every transformation run executes inside a dedicated, isolated folder (`data/uploads/runs/run_<random_id>/`). Stateless instances of contexts, extractors, and engines are spun up fresh on every single API request, eliminating data crossovers.
3. **Automated Record Matching**: Matches the resume parsing output (name/email) against the recruiter CSV rows to automatically resolve the correct Candidate ID (e.g. `CAND-102` for Madhu Rithika) and load relevant database metrics statelessly.
4. **spaCy NLP Extraction Pipeline**: Utilizes Named Entity Recognition (NER), token property mappings, and section segment boundaries to extract precise schemas without hardcoded keywords.
5. **Weighted Evidence Merge Engine**: Combines conflicting values from multiple inputs using source reliability weights, agreement bonuses, and conflict penalties while keeping a complete log of rejected evidence.
6. **Detailed Provenance Lineage**: Tracks field-level source, method, confidence, normalizations, and merge decisions.
7. **Runtime Configuration & Projection**: Fully configurable output schema (`data/output_schema.json`) allows reordering, renamings, required constraints, normalizer configurations, and metadata toggling.

---

## 🛠️ Technology Stack

* **Backend**: FastAPI, Uvicorn, Python 3.10+
* **NLP & Matching**: spaCy (`en_core_web_sm`), RapidFuzz (Levenshtein metrics)
* **Document Extraction**: PyPDF2, python-docx, csv, json, io, urllib
* **Data Validation**: Pydantic v2
* **Frontend**: Single Page Application (SPA), HTML5, Vanilla JS, CSS3, Glassmorphic styling tokens

---

## 📁 Project Structure

```
candidate-transformer/
├── data/
│   ├── output_schema.json       # Runtime Configuration file
│   └── uploads/                 # Temporary uploader storage & Request execution run folders
├── debug/                       # Generated step-by-phase execution trace JSON files (01 to 11)
├── src/
│   ├── core/                    # Ingestion state & Phase context metrics tracker
│   ├── engine/                  # Merger, validator, confidence, projection, and business rules
│   ├── extractors/              # Resume, CSV, and live GitHub API extractors
│   ├── models/                  # Domain Field Pydantic schemas and provenance models
│   ├── normalizers/             # E164 phone formats, Title Cases, and Canonical skills maps
│   └── pipeline.py              # Main orchestrator running the 12-phase pipeline
├── static/
│   └── index.html               # Redesigned glassmorphic 12-section ATS candidate profile dashboard
├── tests/
│   └── test_pipeline.py         # Automated pytest test suites
├── requirements.txt             # Python dependencies
├── server.py                    # FastAPI server entry point
├── main.py                      # CLI entry point
└── README.md                    # This documentation file
```

---

## ⚙️ Prerequisites & Setup

Ensure you have Python 3.10 or higher installed. Follow these steps to set up and run the platform:

### 1. Set Up Virtual Environment

Open your shell (e.g. PowerShell or Bash) in the project root directory:

```bash
# Create virtual environment
python -m venv venv

# Activate on Windows (PowerShell)
venv\Scripts\Activate.ps1

# Activate on Unix/macOS
source venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Download the spaCy NLP Model

```bash
python -m spacy download en_core_web_sm
```

---

## 🏃 Running the Application

### 1. Launch the Web Server
Launch the FastAPI uvicorn server locally:

```bash
python server.py
```
By default, the application runs on **`http://127.0.0.1:8000/`**.

### 2. Run Pipeline via Command Line Interface (CLI)
You can execute the pipeline statelessly for a specific candidate directly from your terminal using `main.py`:

```bash
# General CLI Command Syntax
python main.py --candidate <CANDIDATE_ID> --csv <CSV_PATH> --resume <RESUME_PATHS_COMMA_SEPARATED> --github <GITHUB_URLS_COMMA_SEPARATED>

# Example 1: Ingesting a single candidate with one resume
python main.py --candidate CAND-101 --csv data/recruiter_data.csv --resume data/resume.pdf

# Example 2: Ingesting multiple comma-separated resumes and GitHub profiles
python main.py --candidate CAND-101 --csv data/recruiter_data.csv --resume data/resume.pdf,data/resume2.pdf --github https://github.com/Girikannan2107,https://github.com/anotheruser
```

### 3. Interacting with the SPA Dashboard
1. Open `http://127.0.0.1:8000/` in your browser.
2. Click **Get Started**.
3. **Upload Files**:
   - Drag & drop or browse one or **multiple candidate resumes** (.pdf / .docx).
   - Drag & drop or browse the **Recruiter CSV Export** (e.g. `data/recruiter_data.csv`).
4. **Additional Profiles**: Input one or **multiple comma-separated GitHub URLs** (optional).
5. **Select Ingestion Mode**:
   - *Single Candidate Mode*: Runs transformation on the matched candidate and background pre-loads others.
   - *Multi-Candidate Mode*: Runs transformation for all candidates in parallel and goes directly to the comparison matrix.
6. Click **Run Candidate Transformation** to visualize the ingested profiles.

---

## 🧪 Running Automated Tests

Run the test suite using `pytest` to verify extraction, normalization, merging, entity resolution, and pipeline integration correctness:

```bash
# Run all unit tests
python -m pytest

# Run with verbose logs
python -m pytest -v
```

All 11 tests will execute and verify compliance.

---

## ⚙️ Runtime Projection Configuration (`data/output_schema.json`)

You can alter the pipeline output without modifying python code by editing `data/output_schema.json`. It supports:

* **Toggling Metadata**: Set `"include_provenance": false` or `"include_confidence": false` to strip metrics.
* **On Missing Strategies**: Set `"on_missing"` to `"null"`, `"omit"`, or `"error"` to dictate missing-field actions.
* **Rename Fields**: Define mapping keys to project canonical properties (e.g., mapping `full_name` to `"fullname"` or `years_experience` to `"experience_years"`).

---

## 🔍 Assumptions & Edge Cases Handled

* **Multi-GitHub Profile Auto-Matching**: Comma-separated GitHub URLs are resolved and automatically matched to candidates based on username/name fields.
* **Graceful GitHub Rate Limit Degradation**: If the live GitHub API limits requests, the `GitHubExtractor` logs a warning and yields empty data structures, allowing the pipeline to complete successfully using Resume and CSV details.
* **Path Traversal Protection**: Uploaded filenames are scrubbed and saved using UUID mappings, preventing filesystem directory traversal vulnerabilities (`../../`).
* **Name & Email Fallbacks**: If the candidate resume fails to map an email address, the matching resolver scans row profiles against name parameters to locate matching entries.
* **Null Value Handling**: If a field remains missing, the label remains present on the UI and is outputted as `"Not Available"` (or `null`/omitted according to schema projection rules).
