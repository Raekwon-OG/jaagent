"""
Google Sheets tracking for job applications
"""
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path

try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False

from config import settings

logger = logging.getLogger(__name__)

class SheetsTracker:
    """Manages Google Sheets tracking for job applications"""
    
    def __init__(self):
        if not GSPREAD_AVAILABLE:
            raise ImportError("Google Sheets dependencies not available. Install: pip install gspread google-auth")
        
        self.credentials_file = Path(settings.SHEETS_CREDENTIALS_FILE)
        self.sheet_name = settings.SHEETS_DOC_NAME
        self.worksheet_name = settings.SHEETS_WORKSHEET_NAME
        
        self.gc = None
        self.spreadsheet = None
        self.worksheet = None
        
        # Column headers for the tracking sheet
        self.headers = [
            'JobID', 'Job Title', 'Company', 'Role Category', 'Role Variation',
            'Job Link', 'Fit Score', 'Date Saved', 'Status', 'Folder Path', 'Notes'
        ]
        
        # Initialize connection
        self._initialize_sheets_connection()
        self._ensure_worksheet_exists()
    
    def _initialize_sheets_connection(self):
        """Initialize Google Sheets API connection"""
        
        if not self.credentials_file.exists():
            error_msg = f"Google Sheets credentials file not found: {self.credentials_file}"
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)
        
        try:
            # Define the required scopes
            scopes = [
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]
            
            # Load credentials
            credentials = Credentials.from_service_account_file(
                str(self.credentials_file),
                scopes=scopes
            )
            
            # Initialize gspread client
            self.gc = gspread.authorize(credentials)
            
            logger.info("Successfully connected to Google Sheets API")
            
        except Exception as e:
            logger.error(f"Error initializing Google Sheets connection: {e}")
            raise
    
    def _ensure_worksheet_exists(self):
        """Ensure the tracking spreadsheet and worksheet exist"""
        
        try:
            # Try to open existing spreadsheet
            try:
                self.spreadsheet = self.gc.open(self.sheet_name)
                logger.info(f"Opened existing spreadsheet: {self.sheet_name}")
            except gspread.SpreadsheetNotFound:
                # Create new spreadsheet
                self.spreadsheet = self.gc.create(self.sheet_name)
                logger.info(f"Created new spreadsheet: {self.sheet_name}")
            
            # Try to get the worksheet
            try:
                self.worksheet = self.spreadsheet.worksheet(self.worksheet_name)
                logger.info(f"Using existing worksheet: {self.worksheet_name}")
                
                # Check if headers exist, add if not
                self._ensure_headers()
                
            except gspread.WorksheetNotFound:
                # Create new worksheet
                self.worksheet = self.spreadsheet.add_worksheet(
                    title=self.worksheet_name,
                    rows=1000,
                    cols=len(self.headers)
                )
                logger.info(f"Created new worksheet: {self.worksheet_name}")
                
                # Add headers
                self._add_headers()
            
        except Exception as e:
            logger.error(f"Error ensuring worksheet exists: {e}")
            raise
    
    def _ensure_headers(self):
        """Check if headers exist and add them if missing"""
        
        try:
            # Get first row
            first_row = self.worksheet.row_values(1)
            
            if not first_row or first_row != self.headers:
                logger.info("Headers missing or incorrect, updating...")
                self.worksheet.update('A1', [self.headers])
                
        except Exception as e:
            logger.error(f"Error checking/updating headers: {e}")
    
    def _add_headers(self):
        """Add headers to new worksheet"""
        
        try:
            self.worksheet.update('A1', [self.headers])
            logger.info("Added headers to worksheet")
            
        except Exception as e:
            logger.error(f"Error adding headers: {e}")
            raise
    
    def append_job(self, job_id: str, title: str, company: str, category: str,
                   variation: str, link: str, fit_score: any, status: str,
                   notes: str, folder_path: str) -> bool:
        """
        Append a job application record to the tracking sheet
        Returns True if successful
        """
        
        try:
            # Prepare row data
            current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Format fit score
            if isinstance(fit_score, (int, float)):
                fit_score_str = f"{fit_score:.1f}"
            else:
                fit_score_str = str(fit_score) if fit_score else ""
            
            row_data = [
                job_id,
                title,
                company,
                category,
                variation,
                link,
                fit_score_str,
                current_date,
                status,
                folder_path,
                notes
            ]
            
            # Append the row
            self.worksheet.append_row(row_data)
            
            logger.info(f"Successfully logged job to Google Sheets: {title} at {company}")
            return True
            
        except Exception as e:
            logger.error(f"Error appending job to sheets: {e}")
            return False
    
    def update_job_status(self, job_id: str, new_status: str, notes: str = "") -> bool:
        """
        Update the status of an existing job record
        Returns True if successful
        """
        
        try:
            # Find the job by ID
            job_id_column = self.headers.index('JobID') + 1  # gspread uses 1-based indexing
            
            # Get all values in JobID column
            job_ids = self.worksheet.col_values(job_id_column)
            
            # Find matching row
            for i, existing_id in enumerate(job_ids):
                if existing_id == job_id:
                    row_number = i + 1
                    
                    # Update status and notes
                    status_col = self.headers.index('Status') + 1
                    notes_col = self.headers.index('Notes') + 1
                    
                    updates = [
                        {
                            'range': f'{chr(64 + status_col)}{row_number}',
                            'values': [[new_status]]
                        }
                    ]
                    
                    if notes:
                        updates.append({
                            'range': f'{chr(64 + notes_col)}{row_number}',
                            'values': [[notes]]
                        })
                    
                    self.worksheet.batch_update(updates)
                    
                    logger.info(f"Updated job status: {job_id} -> {new_status}")
                    return True
            
            logger.warning(f"Job ID not found for status update: {job_id}")
            return False
            
        except Exception as e:
            logger.error(f"Error updating job status: {e}")
            return False
    
    def get_job_records(self, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all job records, optionally filtered by status
        Returns list of job dictionaries
        """
        
        try:
            # Get all records
            records = self.worksheet.get_all_records()
            
            # Convert to list of dicts and filter if needed
            job_records = []
            for record in records:
                if status_filter is None or record.get('Status') == status_filter:
                    job_records.append(record)
            
            logger.info(f"Retrieved {len(job_records)} job records from sheets")
            return job_records
            
        except Exception as e:
            logger.error(f"Error retrieving job records: {e}")
            return []
    
    def get_application_stats(self) -> Dict[str, Any]:
        """Get statistics about tracked applications"""
        
        try:
            records = self.get_job_records()
            
            if not records:
                return {
                    'total_jobs': 0,
                    'by_status': {},
                    'by_category': {},
                    'average_fit_score': 0,
                    'recent_applications': 0
                }
            
            # Count by status
            status_counts = {}
            category_counts = {}
            fit_scores = []
            
            # Count recent applications (last 7 days)
            recent_count = 0
            cutoff_date = (datetime.now() - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
            
            for record in records:
                # Status counts
                status = record.get('Status', 'unknown')
                status_counts[status] = status_counts.get(status, 0) + 1
                
                # Category counts
                category = record.get('Role Category', 'Unknown')
                category_counts[category] = category_counts.get(category, 0) + 1
                
                # Fit scores
                fit_score = record.get('Fit Score', '')
                if fit_score and fit_score != '':
                    try:
                        fit_scores.append(float(fit_score))
                    except ValueError:
                        pass
                
                # Recent applications
                date_saved = record.get('Date Saved', '')
                if date_saved and date_saved.split()[0] >= cutoff_date:
                    recent_count += 1
            
            return {
                'total_jobs': len(records),
                'by_status': status_counts,
                'by_category': category_counts,
                'average_fit_score': sum(fit_scores) / len(fit_scores) if fit_scores else 0,
                'recent_applications': recent_count
            }
            
        except Exception as e:
            logger.error(f"Error calculating application stats: {e}")
            return {'error': str(e)}
    
    def validate_setup(self) -> List[str]:
        """Validate Google Sheets setup and return any issues"""
        
        issues = []
        
        # Check credentials file
        if not self.credentials_file.exists():
            issues.append(f"Google Sheets credentials file not found: {self.credentials_file}")
            return issues
        
        # Test connection
        try:
            if not self.gc:
                self._initialize_sheets_connection()
            
            # Test spreadsheet access
            if not self.spreadsheet:
                self._ensure_worksheet_exists()
            
            # Test write permissions by appending a test row and removing it
            test_job_id = f"test_{int(datetime.now().timestamp())}"
            success = self.append_job(
                job_id=test_job_id,
                title="Test Job",
                company="Test Company",
                category="Test Category",
                variation="Test Variation",
                link="https://test.com",
                fit_score=9.0,
                status="test",
                notes="Validation test",
                folder_path="/test/path"
            )
            
            if success:
                # Remove the test row
                try:
                    records = self.worksheet.get_all_records()
                    for i, record in enumerate(records):
                        if record.get('JobID') == test_job_id:
                            self.worksheet.delete_rows(i + 2)  # +2 because headers are row 1
                            break
                except Exception:
                    pass  # If deletion fails, that's ok for validation
            else:
                issues.append("Cannot write to Google Sheets - check permissions")
            
        except Exception as e:
            issues.append(f"Google Sheets connection failed: {e}")
        
        return issues
    
    def get_spreadsheet_url(self) -> Optional[str]:
        """Get the URL of the tracking spreadsheet"""
        
        if self.spreadsheet:
            return f"https://docs.google.com/spreadsheets/d/{self.spreadsheet.id}"
        return None
    
    def export_to_csv(self, output_path: Path) -> bool:
        """Export tracking data to CSV file"""
        
        try:
            records = self.get_job_records()
            
            if not records:
                logger.warning("No records to export")
                return False
            
            import csv
            
            with open(output_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=self.headers)
                writer.writeheader()
                
                for record in records:
                    # Ensure all headers are present
                    row = {}
                    for header in self.headers:
                        row[header] = record.get(header, '')
                    writer.writerow(row)
            
            logger.info(f"Exported {len(records)} records to {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error exporting to CSV: {e}")
            return False


# Factory function
def create_sheets_tracker() -> SheetsTracker:
    """Create a configured sheets tracker instance"""
    return SheetsTracker()


# Global tracker instance
_global_sheets_tracker: Optional[SheetsTracker] = None

def get_global_sheets_tracker() -> SheetsTracker:
    """Get or create the global sheets tracker instance"""
    global _global_sheets_tracker
    if _global_sheets_tracker is None:
        _global_sheets_tracker = create_sheets_tracker()
    return _global_sheets_tracker


# Convenience functions
def log_job_application(job_id: str, title: str, company: str, category: str,
                       variation: str, link: str, fit_score: any, status: str,
                       notes: str = "", folder_path: str = "") -> bool:
    """Quick function to log job application"""
    tracker = get_global_sheets_tracker()
    return tracker.append_job(job_id, title, company, category, variation,
                            link, fit_score, status, notes, folder_path)

def update_application_status(job_id: str, new_status: str, notes: str = "") -> bool:
    """Quick function to update application status"""
    tracker = get_global_sheets_tracker()
    return tracker.update_job_status(job_id, new_status, notes)

def get_application_statistics() -> Dict[str, Any]:
    """Quick function to get application statistics"""
    tracker = get_global_sheets_tracker()
    return tracker.get_application_stats()