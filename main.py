import argparse
import logging
import json
from src.pipeline import CandidatePipeline

# Configure structured logging
def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

def main():
    setup_logging()
    logger = logging.getLogger("CLI")
    
    # Setup Argument Parser
    parser = argparse.ArgumentParser(description="Eightfold Multi-Source Candidate Data Transformer")
    parser.add_argument("--csv", help="Path to recruiter CSV export", type=str)
    parser.add_argument("--github", help="GitHub Profile URL", type=str)
    parser.add_argument("--resume", help="Path to Resume PDF", type=str) # <--- NEW ARGUMENT
    parser.add_argument("--ats", help="Path to ATS JSON export", type=str)
    parser.add_argument("--config", help="Path to output schema config JSON", required=True, type=str)
    parser.add_argument("--candidate_id", help="Unique ID for the candidate", default="CAND-8832", type=str)
    
    args = parser.parse_args()

    logger.info("Initializing Pipeline...")
    pipeline = CandidatePipeline(config_path=args.config)
    
    try:
        # Pass the resume_path to the run method
        result = pipeline.run(
            candidate_id=args.candidate_id,
            csv_path=args.csv,
            github_url=args.github,
            resume_path=args.resume,
            ats_path=args.ats
        )
        
        # Output the pipeline statistics report to logs
        if "pipeline_report" in result:
            logger.info("Pipeline Execution Complete. Report:")
            logger.info(json.dumps(result["pipeline_report"], indent=2))
            
        # Output the exact schema-valid JSON
        print("\n" + "="*60)
        print("=== FINAL PROJECTED CANONICAL PROFILE ===")
        print("="*60)
        projected = result.get("projected_profile", {})
        print(json.dumps(projected, indent=2))
        print("="*60 + "\n")
        
    except Exception as e:
        logger.error(f"Pipeline execution encountered a critical failure: {e}")

if __name__ == "__main__":
    main()