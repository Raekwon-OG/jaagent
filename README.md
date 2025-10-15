# Job Application Agent

An intelligent job application automation system that scrapes job postings, tailors resumes and cover letters using AI, and manages applications with sophisticated filtering and tracking. Inspired by the desire to automate majority of the steps in my job search workflow which I believe many others may also find useful.
If you would like to contribute to this project please email me: demilade_odumosu@outlook.com || thefitprogrammer@gmail.com 

## License
This project is licensed under a custom license. Public use is permitted for personal use / reference only. Redistribution, modification, or commercial use is prohibited without permission. See [LICENSE](./LICENSE) for details.

## Features

- **Smart Job Filtering**: Automatically filters jobs based on location and visa sponsorship requirements
- **AI-Powered Tailoring**: Uses GPT-4 to customize resumes and cover letters for each application
- **Role Detection**: Automatically categorizes jobs using embeddings and keyword matching
- **Dual Storage**: Store files locally or in Google Drive
- **Batch Processing**: Process multiple jobs with configurable limits
- **Google Sheets Tracking**: Automatically log all applications with detailed metadata
- **International Job Seeker Support**: Built-in location and work permit filtering

## Prerequisites

1. **Python 3.8+**
2. **OpenAI API Key** - Get from [OpenAI Platform](https://platform.openai.com/)
3. **Google Service Account** - For Sheets and Drive API access
4. **Base Resume Templates** - One `.docx` file per role category

## Installation

1. **Clone or download the project**:
```bash
git clone <repository-url>
cd job_application_agent
```

2. **Install dependencies**:
```bash
pip install -r requirements.txt
```

3. **Set up environment variables**:
```bash
# Create .env file
cp .env.template .env
```

4. **Configure Google API credentials**:
   - Create a Google Cloud Project
   - Enable Google Sheets API and Google Drive API
   - Create a Service Account and download credentials
   - Save credentials as:
     - `config/sheets_credentials.json`
     - `config/drive_credentials.json` (if using cloud storage)

## Configuration

### 1. Basic Settings (`.env`)

Edit the following key settings in your env:

```bash
# Your information
APPLICANT_COUNTRY = "Nigeria"  # Your current country
CANDIDATE_NAME = "Your Full Name"
CANDIDATE_EMAIL_PHONE = "your.email@example.com\n+234-XXX-XXX-XXXX"

# Processing limits
MAX_JOBS_PER_RUN = 5  # Maximum jobs to process per execution

# Storage mode
STORAGE_MODE = "local"  # or "cloud" for Google Drive
```

### 2. Base Resume Templates

Create base resume templates for each role category (Example below):

```
base_resumes/
├── Full Stack Web Developer.docx
├── IT Specialist.docx
├── IT Manager.docx
├── IT Support Engineer.docx
├── Automation & Integration Engineer.docx
├── Software Engineer.docx
├── Linux Engineer.docx
└── Jira Administrator.docx
```

**Important**: Each base resume should contain:
- Professional Summary section
- Experience/Work History section
- Skills, Education, and other sections

The agent will only modify the Summary and Experience sections during tailoring.

### 3. Job Sources (Optional)

Create `config/job_sources.csv` with custom job sites to scrape:

```csv
site_name,base_url,search_params
Indeed,https://indeed.com/jobs,q={keywords}&l={location}
RemoteOK,https://remoteok.io,{keywords}
AngelList,https://angel.co/jobs,{keywords}
```

If this file is empty or missing, the agent will fall back to LinkedIn scraping.

### 4. Google Sheets Setup

1. Create a new Google Sheet named "Job Application Tracker"
2. The agent will automatically create headers:
   ```
   JobID | Job Title | Company | Role Category | Role Variation | Job Link | Fit Score | Date Saved | Status | Folder Path | Notes
   ```

## Usage

### Command Line Interface

**Process jobs from CSV sources**:
```bash
python main.py --batch
```

**Process a specific job URL**:
```bash
python main.py --url "https://linkedin.com/jobs/view/12345"
```

**Process job description from file**:
```bash
python main.py --jd-file job_description.txt --title "Software Engineer" --company "Tech Corp" --link "https://example.com/job"
```

**Check configuration**:
```bash
python main.py --validate
```

### Processing Flow

1. **Job Collection**: Scrapes or accepts job postings
2. **Early Filtering**: 
   - Checks work permit requirements vs your location
   - Filters out incompatible locations
3. **Role Detection**: Maps job titles to predefined categories using AI
4. **Resume Tailoring**: Customizes resume summary and experience sections
5. **Fit Scoring**: AI scores job fit against tailored resume (0-10 scale)
6. **Document Generation**: Creates tailored resume and cover letter (if score ≥ 8.5)
7. **Storage**: Saves files locally or to Google Drive
8. **Tracking**: Logs application details to Google Sheets

### Output Structure

**Local Storage** (`data/applications/`):
```
CompanyName_RoleCategory_JobID/
├── resume.docx
├── resume.pdf
├── cover_letter.docx
├── cover_letter.pdf
└── job_details.json
```

**Google Drive** (if cloud mode):
```
Job Applications/
└── CompanyName_RoleCategory_JobID/
    ├── resume.docx
    ├── resume.pdf
    ├── cover_letter.docx
    ├── cover_letter.pdf
    └── job_details.json
```

## Filtering Logic

### Location & Visa Sponsorship

The agent implements sophisticated filtering for international job seekers:

**Jobs are IGNORED if**:
- Job is in a different country than yours AND
- Contains restrictive terms like "must have work permit" AND
- No positive sponsorship indicators found

**Jobs are PROCESSED if**:
- Job is in your country, OR
- Job is international with sponsorship indicators like "visa sponsorship available"

### Role Detection

1. **Keyword Matching**: First tries exact/partial matches on job titles
2. **Semantic Matching**: Uses embeddings to find similar role variations
3. **Threshold**: Requires 80%+ similarity to assign a category
4. **Fallback**: Unknown roles are logged but ignored

### Fit Scoring

- AI analyzes tailored resume against job description
- Scores from 0-10 based on requirements alignment
- Only jobs scoring 8.5+ generate application documents
- Lower scores are logged as "ignored (fit<8.5)"

## Customization

### Adding New Role Categories

1. Add new category to `config/roles.json`:
```json
"New Role Category": [
  "Role Variation 1",
  "Role Variation 2"
]
```

2. Create base resume: `base_resumes/New Role Category.docx`

3. Update `schemas/job_schema.json` enum list

### Modifying Prompts

Edit prompt templates in `prompts/`:
- `align_resume_cover_letter.txt` - Resume tailoring and cover letter generation
- `score_fit.txt` - Job fit scoring logic

### Custom Job Sources

Add job sites to `config/job_sources.csv` with appropriate search parameters.

## Troubleshooting

### Common Issues

1. **"No OpenAI API Key"**: Set `OPENAI_API_KEY` environment variable
2. **"Google credentials not found"**: Ensure service account JSON files are in `config/`
3. **"Role Unknown"**: Job title doesn't match any category - add to `roles.json`
4. **"PDF generation failed"**: Install appropriate PDF conversion dependencies for your OS

### Debug Mode

Enable debug mode in `config/settings.py`:
```python
DEBUG_MODE = True
SAVE_DEBUG_DATA = True
```

This saves intermediate processing data to `data/debug/`.

### Validation

Run configuration validation:
```bash
python main.py --validate
```

## File Structure

```
job_application_agent/
├── config/                     # Configuration files
├── base_resumes/              # Resume templates per role
├── prompts/                   # AI prompt templates
├── data/                      # Output and debug data
├── utils/                     # Utility modules
├── services/                  # Core services (AI, storage)
├── schemas/                   # Data schemas
├── main.py                    # Main orchestrator
├── requirements.txt           # Python dependencies
└── README.md                 # This file
```

## Security Notes

- Never commit API keys or credential files to version control
- Use environment variables for sensitive configuration
- Ensure Google service account has minimal required permissions
- Review generated content before submitting applications

## Rate Limits & Costs

- **OpenAI API**: Each job uses ~2-4 API calls (embedding, tailoring, scoring)
- **Google APIs**: Minimal usage for Sheets logging and Drive storage
- **Job Sites**: Respect robots.txt and implement delays between requests

## Contributing

1. Follow existing code structure and naming conventions
2. Add tests for new functionality
3. Update documentation for configuration changes
4. Test with various job posting formats

## License

This project is for personal use. Ensure compliance with job site terms of service when scraping.

## Support

For issues:
1. Check the troubleshooting section
2. Validate your configuration
3. Enable debug mode to investigate processing steps
4. Review logs in the console output

---

**Note**: This tool is designed to assist with job applications, not to spam employers. Use responsibly and always review generated content before submission.