"""
Job processing counter and limits management
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from pathlib import Path
from dataclasses import dataclass, asdict
from config import settings

logger = logging.getLogger(__name__)

@dataclass
class JobProcessingStats:
    """Statistics for job processing session"""
    total_scraped: int = 0
    total_processed: int = 0
    successful_applications: int = 0
    ignored_role_unknown: int = 0
    ignored_work_permit: int = 0
    ignored_low_fit: int = 0
    ignored_duplicate: int = 0
    session_start_time: Optional[str] = None
    session_end_time: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'JobProcessingStats':
        return cls(**data)

class JobCounter:
    """Manages job processing limits and tracking"""
    
    def __init__(self, max_jobs_per_run: Optional[int] = None):
        self.max_jobs_per_run = max_jobs_per_run or settings.MAX_JOBS_PER_RUN
        self.stats = JobProcessingStats()
        self.processed_jobs_file = Path(settings.PROCESSED_JOBS_FILE)
        self.session_jobs: List[str] = []  # Track job IDs processed this session
        self.duplicate_check_data: Dict[str, Dict] = {}
        
        # Ensure directory exists
        self.processed_jobs_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Load existing processed jobs for duplicate detection
        self._load_processed_jobs()
        
        # Initialize session
        self.start_session()
    
    def start_session(self):
        """Start a new processing session"""
        self.stats.session_start_time = datetime.now().isoformat()
        logger.info(f"Started job processing session with limit: {self.max_jobs_per_run}")
    
    def end_session(self):
        """End the current processing session"""
        self.stats.session_end_time = datetime.now().isoformat()
        self._save_session_summary()
        logger.info(f"Ended job processing session. Successful applications: {self.stats.successful_applications}")
    
    def _load_processed_jobs(self):
        """Load previously processed jobs for duplicate detection"""
        try:
            if self.processed_jobs_file.exists():
                with open(self.processed_jobs_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.duplicate_check_data = data.get('processed_jobs', {})
                    logger.info(f"Loaded {len(self.duplicate_check_data)} previously processed jobs")
            else:
                self.duplicate_check_data = {}
                logger.info("No previous job processing data found")
        except Exception as e:
            logger.error(f"Error loading processed jobs: {e}")
            self.duplicate_check_data = {}
    
    def _save_processed_jobs(self):
        """Save processed jobs data"""
        try:
            data = {
                'last_updated': datetime.now().isoformat(),
                'processed_jobs': self.duplicate_check_data,
                'total_processed_count': len(self.duplicate_check_data)
            }
            
            with open(self.processed_jobs_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            logger.error(f"Error saving processed jobs: {e}")
    
    def _save_session_summary(self):
        """Save session summary for analysis"""
        try:
            summary_file = self.processed_jobs_file.parent / f"session_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            
            session_data = {
                'session_stats': self.stats.to_dict(),
                'configuration': {
                    'max_jobs_per_run': self.max_jobs_per_run,
                    'applicant_country': settings.APPLICANT_COUNTRY,
                    'fit_score_threshold': settings.FIT_SCORE_THRESHOLD
                },
                'processed_job_ids': self.session_jobs
            }
            
            with open(summary_file, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, indent=2, ensure_ascii=False)
                
            logger.info(f"Session summary saved to: {summary_file}")
            
        except Exception as e:
            logger.error(f"Error saving session summary: {e}")
    
    def increment_scraped(self, count: int = 1):
        """Increment scraped jobs counter"""
        self.stats.total_scraped += count
        logger.debug(f"Total scraped jobs: {self.stats.total_scraped}")
    
    def increment_processed(self, count: int = 1):
        """Increment processed jobs counter"""
        self.stats.total_processed += count
        logger.debug(f"Total processed jobs: {self.stats.total_processed}")
    
    def is_duplicate_job(self, job_id: str, job_title: str, company_name: str, job_link: str) -> bool:
        """Check if job has been processed before"""
        
        # Check by exact job ID
        if job_id in self.duplicate_check_data:
            return True
        
        # Check by URL (some sites reuse URLs with different IDs)
        for existing_id, job_data in self.duplicate_check_data.items():
            if job_data.get('job_link') == job_link:
                return True
        
        # Check by title + company combination (catch reposts)
        job_signature = f"{job_title.lower().strip()}_{company_name.lower().strip()}"
        for existing_id, job_data in self.duplicate_check_data.items():
            existing_signature = f"{job_data.get('job_title', '').lower().strip()}_{job_data.get('company_name', '').lower().strip()}"
            if job_signature == existing_signature:
                # Additional check: only consider duplicate if posted within last 30 days
                if self._is_recent_posting(job_data.get('processed_date')):
                    return True
        
        return False
    
    def _is_recent_posting(self, processed_date_str: Optional[str]) -> bool:
        """Check if a job was processed recently (within 30 days)"""
        if not processed_date_str:
            return False
        
        try:
            processed_date = datetime.fromisoformat(processed_date_str.replace('Z', '+00:00'))
            cutoff_date = datetime.now() - timedelta(days=30)
            return processed_date > cutoff_date
        except Exception:
            return False
    
    def record_job_attempt(self, job_id: str, job_title: str, company_name: str, 
                          job_link: str, status: str, ignore_reason: Optional[str] = None):
        """Record a job processing attempt"""
        
        # Add to duplicate check data
        self.duplicate_check_data[job_id] = {
            'job_title': job_title,
            'company_name': company_name,
            'job_link': job_link,
            'status': status,
            'ignore_reason': ignore_reason,
            'processed_date': datetime.now().isoformat()
        }
        
        # Track this session
        self.session_jobs.append(job_id)
        
        # Update counters based on status
        if status == "ready_to_apply":
            self.stats.successful_applications += 1
        elif status == "ignored":
            if ignore_reason == "role=Unknown":
                self.stats.ignored_role_unknown += 1
            elif ignore_reason == "work-permit-only" or ignore_reason == "location-incompatible":
                self.stats.ignored_work_permit += 1
            elif ignore_reason == "fit<8.5":
                self.stats.ignored_low_fit += 1
            elif ignore_reason == "duplicate":
                self.stats.ignored_duplicate += 1
        
        # Save after each job to prevent data loss
        self._save_processed_jobs()
        
        logger.info(f"Recorded job attempt: {job_title} at {company_name} - Status: {status}")
    
    def record_duplicate_job(self, job_id: str, job_title: str, company_name: str):
        """Record a duplicate job encounter"""
        self.stats.ignored_duplicate += 1
        logger.info(f"Duplicate job detected: {job_title} at {company_name}")
    
    def can_process_more_jobs(self) -> bool:
        """Check if we can process more jobs based on limits"""
        return self.stats.successful_applications < self.max_jobs_per_run
    
    def get_remaining_job_slots(self) -> int:
        """Get number of remaining job slots for this session"""
        return max(0, self.max_jobs_per_run - self.stats.successful_applications)
    
    def should_continue_scraping(self, max_scrape_limit: Optional[int] = None) -> bool:
        """Check if scraping should continue based on limits"""
        scrape_limit = max_scrape_limit or settings.MAX_SCRAPE_LIMIT
        
        # Stop if we've reached the successful applications limit
        if not self.can_process_more_jobs():
            return False
        
        # Stop if we've scraped too many jobs without success
        if self.stats.total_scraped >= scrape_limit:
            logger.warning(f"Reached scraping limit of {scrape_limit} jobs")
            return False
        
        return True
    
    def get_session_summary(self) -> Dict:
        """Get summary of current session"""
        duration = None
        if self.stats.session_start_time:
            start_time = datetime.fromisoformat(self.stats.session_start_time)
            current_time = datetime.now()
            duration = str(current_time - start_time)
        
        success_rate = 0
        if self.stats.total_processed > 0:
            success_rate = (self.stats.successful_applications / self.stats.total_processed) * 100
        
        return {
            'session_stats': self.stats.to_dict(),
            'session_duration': duration,
            'success_rate_percentage': round(success_rate, 2),
            'remaining_slots': self.get_remaining_job_slots(),
            'can_process_more': self.can_process_more_jobs(),
            'jobs_processed_this_session': len(self.session_jobs)
        }
    
    def get_processing_efficiency_report(self) -> Dict:
        """Generate efficiency report for optimization"""
        total_ignored = (self.stats.ignored_role_unknown + 
                        self.stats.ignored_work_permit + 
                        self.stats.ignored_low_fit + 
                        self.stats.ignored_duplicate)
        
        efficiency_metrics = {
            'total_jobs_examined': self.stats.total_scraped,
            'total_jobs_processed': self.stats.total_processed,
            'successful_applications': self.stats.successful_applications,
            'total_ignored': total_ignored,
            'processing_funnel': {
                'scraped_to_processed_rate': (self.stats.total_processed / max(1, self.stats.total_scraped)) * 100,
                'processed_to_success_rate': (self.stats.successful_applications / max(1, self.stats.total_processed)) * 100,
                'overall_success_rate': (self.stats.successful_applications / max(1, self.stats.total_scraped)) * 100
            },
            'ignore_reasons_breakdown': {
                'unknown_role': self.stats.ignored_role_unknown,
                'work_permit_issues': self.stats.ignored_work_permit,
                'low_fit_score': self.stats.ignored_low_fit,
                'duplicates': self.stats.ignored_duplicate
            }
        }
        
        # Add recommendations
        recommendations = []
        
        if self.stats.ignored_role_unknown > self.stats.successful_applications:
            recommendations.append("Consider expanding role categories in roles.json")
        
        if self.stats.ignored_work_permit > self.stats.successful_applications:
            recommendations.append("Consider adjusting location filtering or expanding target countries")
        
        if self.stats.ignored_low_fit > self.stats.successful_applications:
            recommendations.append("Consider lowering fit score threshold or improving base resumes")
        
        if efficiency_metrics['processing_funnel']['overall_success_rate'] < 10:
            recommendations.append("Low overall success rate - review filtering criteria and job sources")
        
        efficiency_metrics['recommendations'] = recommendations
        
        return efficiency_metrics
    
    def cleanup_old_processed_jobs(self, days_to_keep: int = 90):
        """Clean up old processed job records to prevent file from growing too large"""
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)
        
        cleaned_data = {}
        removed_count = 0
        
        for job_id, job_data in self.duplicate_check_data.items():
            processed_date_str = job_data.get('processed_date')
            if processed_date_str:
                try:
                    processed_date = datetime.fromisoformat(processed_date_str.replace('Z', '+00:00'))
                    if processed_date > cutoff_date:
                        cleaned_data[job_id] = job_data
                    else:
                        removed_count += 1
                except Exception:
                    # Keep job if date parsing fails
                    cleaned_data[job_id] = job_data
            else:
                # Keep job if no date
                cleaned_data[job_id] = job_data
        
        if removed_count > 0:
            self.duplicate_check_data = cleaned_data
            self._save_processed_jobs()
            logger.info(f"Cleaned up {removed_count} old job records (older than {days_to_keep} days)")
        
        return removed_count


# Factory function for easy access
def create_job_counter(max_jobs_per_run: Optional[int] = None) -> JobCounter:
    """Create a configured job counter instance"""
    return JobCounter(max_jobs_per_run)


# Convenience function for checking limits
def check_processing_limits(counter: JobCounter) -> Dict[str, bool]:
    """Quick check of all processing limits"""
    return {
        'can_process_more_jobs': counter.can_process_more_jobs(),
        'should_continue_scraping': counter.should_continue_scraping(),
        'remaining_slots': counter.get_remaining_job_slots(),
        'reached_scrape_limit': counter.stats.total_scraped >= settings.MAX_SCRAPE_LIMIT
    }


# Global counter instance (created when needed)
_global_counter: Optional[JobCounter] = None

def get_global_counter() -> JobCounter:
    """Get or create the global job counter instance"""
    global _global_counter
    if _global_counter is None:
        _global_counter = create_job_counter()
    return _global_counter

def reset_global_counter():
    """Reset the global counter (useful for testing)"""
    global _global_counter
    if _global_counter:
        _global_counter.end_session()
    _global_counter = None