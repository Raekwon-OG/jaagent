"""
Configuration settings for Job Application Agent
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# =============================================================================
# API KEYS & CREDENTIALS
# =============================================================================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# =============================================================================
# APPLICANT CONFIGURATION
# =============================================================================
# Applicant's current country (ISO 2-letter code or full name)
# This is used for location-based filtering of job opportunities
APPLICANT_COUNTRY = os.getenv("APPLICANT_COUNTRY", "Nigeria")
APPLICANT_COUNTRY_CODE = os.getenv("APPLICANT_COUNTRY_CODE", "NG")  # ISO 2-letter code

# Applicant contact information for cover letters
CANDIDATE_NAME = os.getenv("CANDIDATE_NAME", "Your Full Name")
CANDIDATE_ADDRESS = os.getenv("CANDIDATE_ADDRESS", """Your Street Address
Your City, State/Province
Your Country, Postal Code""")
CANDIDATE_EMAIL_PHONE = os.getenv("CANDIDATE_EMAIL_PHONE", """your.email@example.com
+234-XXX-XXX-XXXX""")

# =============================================================================
# STORAGE CONFIGURATION
# =============================================================================
# Storage mode: "local" or "cloud" (Google Drive)
STORAGE_MODE = os.getenv("STORAGE_MODE", "local")  # Options: "local", "cloud"

# Local storage paths
BASE_RESUMES_DIR = os.getenv("BASE_RESUMES_DIR", "base_resumes")
APPLICATIONS_DIR = os.getenv("APPLICATIONS_DIR", "data/applications")
PROCESSED_JOBS_FILE = os.getenv("PROCESSED_JOBS_FILE", "data/processed_jobs.json")

# Google Drive configuration (for cloud mode)
GOOGLE_DRIVE_FOLDER_NAME = os.getenv("GOOGLE_DRIVE_FOLDER_NAME", "Job Applications")  # Main folder in Google Drive
GOOGLE_DRIVE_SUBFOLDER_STRUCTURE = os.getenv("GOOGLE_DRIVE_SUBFOLDER_STRUCTURE", "true").lower() == "true"  # Create company/role subfolders

# =============================================================================
# JOB PROCESSING LIMITS
# =============================================================================
# Maximum number of jobs to process per run (jobs that reach Google Sheets logging)
MAX_JOBS_PER_RUN = int(os.getenv("MAX_JOBS_PER_RUN", "5"))

# Maximum number of job postings to scrape before filtering (prevents infinite scraping)
MAX_SCRAPE_LIMIT = int(os.getenv("MAX_SCRAPE_LIMIT", "50"))
SCRAPE_SOURCE_MULTIPLIER = 3  # how many candidates per source = MAX_SCRAPE_LIMIT * SCRAPE_SOURCE_MULTIPLIER

# =============================================================================
# JOB SOURCES CONFIGURATION
# =============================================================================
# CSV file containing job source URLs
JOB_SOURCES_CSV = os.getenv("JOB_SOURCES_CSV", "config/job_sources.csv")

# Default LinkedIn search parameters (used when CSV is empty or missing)
LINKEDIN_FALLBACK = {
    "base_url": os.getenv("LINKEDIN_BASE_URL", "https://www.linkedin.com/jobs/search"),
    "default_location": os.getenv("LINKEDIN_DEFAULT_LOCATION", "Worldwide"),
    "default_keywords": os.getenv("LINKEDIN_DEFAULT_KEYWORDS", "software engineer OR IT support OR full stack developer"),
    "experience_levels": os.getenv("LINKEDIN_EXPERIENCE_LEVELS", "entry,associate,mid-senior").split(","),
}

# =============================================================================
# GOOGLE SERVICES CONFIGURATION
# =============================================================================
# Google Sheets
SHEETS_CREDENTIALS_FILE = os.getenv("SHEETS_CREDENTIALS_FILE", "config/sheets_credentials.json")
SHEETS_DOC_NAME = os.getenv("SHEETS_DOC_NAME", "Job Application Tracker")
SHEETS_WORKSHEET_NAME = os.getenv("SHEETS_WORKSHEET_NAME", "Sheet1")

# Google Drive (for cloud storage mode)
DRIVE_CREDENTIALS_FILE = os.getenv("DRIVE_CREDENTIALS_FILE", "config/drive_credentials.json")

# =============================================================================
# AI MODEL CONFIGURATION
# =============================================================================
# OpenAI models
CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4o-mini")  # For tailoring and scoring
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")  # For role detection

# Role detection parameters
SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.80"))  # Minimum cosine similarity for role matching
FIT_SCORE_THRESHOLD = float(os.getenv("FIT_SCORE_THRESHOLD", "8.5"))   # Minimum fit score to proceed with application

# =============================================================================
# LOCATION & WORK PERMIT FILTERING
# =============================================================================
# Terms indicating job requires local work authorization
_restrictive_terms_env = os.getenv("RESTRICTIVE_LOCAL_TERMS", 
    "must have valid work permit,must be authorized to work,local applicants only,must already reside in,no visa sponsorship,must have work authorization,only citizens,permanent residents only,must be eligible to work,work permit required,authorization to work required,local candidates only,residents only,no sponsorship available")
RESTRICTIVE_LOCAL_TERMS = [term.strip() for term in _restrictive_terms_env.split(",")]

# Terms indicating job offers sponsorship/relocation
_positive_terms_env = os.getenv("POSITIVE_SPONSORSHIP_TERMS",
    "visa sponsorship available,open to international applicants,work permit sponsorship,relocation assistance,willing to sponsor,global applicants welcome,sponsorship provided,visa support available,international candidates welcome,work authorization sponsorship,H1B sponsorship,visa assistance,sponsorship opportunities")
POSITIVE_SPONSORSHIP_TERMS = [term.strip() for term in _positive_terms_env.split(",")]

# Countries that commonly offer visa sponsorship for tech roles
_sponsorship_countries_env = os.getenv("SPONSORSHIP_FRIENDLY_COUNTRIES",
    "United States,Canada,United Kingdom,Germany,Netherlands,Sweden,Denmark,Norway,Australia,New Zealand,Singapore,Ireland,Switzerland,France,Austria,Belgium,Luxembourg")
SPONSORSHIP_FRIENDLY_COUNTRIES = [country.strip() for country in _sponsorship_countries_env.split(",")]

# =============================================================================
# FILE GENERATION SETTINGS
# =============================================================================
# Whether to generate PDF files (set to False for headless environments)
GENERATE_PDF = os.getenv("GENERATE_PDF", "true").lower() == "true"

# Document formats
RESUME_FILENAME = os.getenv("RESUME_FILENAME", "resume")
COVER_LETTER_FILENAME = os.getenv("COVER_LETTER_FILENAME", "cover_letter")
JOB_DETAILS_FILENAME = os.getenv("JOB_DETAILS_FILENAME", "job_details.json")

# =============================================================================
# LOGGING & DEBUGGING
# =============================================================================
# Enable verbose logging
DEBUG_MODE = os.getenv("DEBUG_MODE", "true").lower() == "true"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")  # DEBUG, INFO, WARNING, ERROR

# Save intermediate processing data for debugging
SAVE_DEBUG_DATA = os.getenv("SAVE_DEBUG_DATA", "true").lower() == "true"
DEBUG_DATA_DIR = os.getenv("DEBUG_DATA_DIR", "data/debug")

# =============================================================================
# PROMPTS CONFIGURATION
# =============================================================================
PROMPTS_DIR = os.getenv("PROMPTS_DIR", "prompts")
ALIGN_PROMPT_FILE = f"{PROMPTS_DIR}/{os.getenv('ALIGN_PROMPT_FILENAME', 'align_resume_cover_letter.txt')}"
SCORE_PROMPT_FILE = f"{PROMPTS_DIR}/{os.getenv('SCORE_PROMPT_FILENAME', 'score_fit.txt')}"

# =============================================================================
# VALIDATION & HELPERS
# =============================================================================
def validate_config():
    """Validate configuration settings"""
    errors = []
    
    if not OPENAI_API_KEY:
        errors.append("OPENAI_API_KEY is required")
    
    if STORAGE_MODE not in ["local", "cloud"]:
        errors.append("STORAGE_MODE must be 'local' or 'cloud'")
    
    if STORAGE_MODE == "cloud" and not Path(DRIVE_CREDENTIALS_FILE).exists():
        errors.append(f"Drive credentials file not found: {DRIVE_CREDENTIALS_FILE}")
    
    if not Path(SHEETS_CREDENTIALS_FILE).exists():
        errors.append(f"Sheets credentials file not found: {SHEETS_CREDENTIALS_FILE}")
    
    if MAX_JOBS_PER_RUN <= 0:
        errors.append("MAX_JOBS_PER_RUN must be greater than 0")
    
    if FIT_SCORE_THRESHOLD < 0 or FIT_SCORE_THRESHOLD > 10:
        errors.append("FIT_SCORE_THRESHOLD must be between 0 and 10")
    
    return errors

def get_storage_path(company_name: str, role_category: str, job_id: str) -> str:
    """Generate storage path based on storage mode"""
    folder_name = f"{company_name}_{role_category}_{job_id}".replace(" ", "_")
    
    if STORAGE_MODE == "local":
        return f"{APPLICATIONS_DIR}/{folder_name}"
    else:
        return f"{GOOGLE_DRIVE_FOLDER_NAME}/{folder_name}"

# =============================================================================
# INITIALIZE DIRECTORIES
# =============================================================================
def ensure_directories():
    """Create necessary directories if they don't exist"""
    directories = [
        APPLICATIONS_DIR,
        BASE_RESUMES_DIR,
        PROMPTS_DIR,
        "data",
        "config"
    ]
    
    if SAVE_DEBUG_DATA:
        directories.append(DEBUG_DATA_DIR)
    
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)