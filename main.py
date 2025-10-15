#!/usr/bin/env python3
"""
Job Application Agent - Main Orchestrator
Automated job application system with AI-powered tailoring and intelligent filtering
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

# Configure logging first
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('job_agent.log')
    ]
)

logger = logging.getLogger(__name__)

# Import application modules
try:
    from config import settings
    from utils.filters import create_job_filter
    from utils.job_counter import get_global_counter, reset_global_counter
    from utils.embeddings import get_global_detector
    from utils.sheets_tracker import get_global_sheets_tracker
    from services.storage_service import get_global_storage_service
    from services.tailoring_service import get_global_tailoring_service
    from services.scoring_service import get_global_scoring_service
    from utils.scraper import create_job_scraper
    
except ImportError as e:
    logger.error(f"Failed to import required modules: {e}")
    logger.error("Please ensure all dependencies are installed: pip install -r requirements.txt")
    sys.exit(1)

class JobApplicationAgent:
    """Main orchestrator for the job application automation system"""
    
    def __init__(self):
        """Initialize the agent with all required services"""
        logger.info("Initializing Job Application Agent...")
        
        try:
            # Initialize core services
            self.job_filter = create_job_filter()
            self.job_counter = get_global_counter()
            self.role_detector = get_global_detector()
            self.storage_service = get_global_storage_service()
            self.tailoring_service = get_global_tailoring_service()
            self.scoring_service = get_global_scoring_service()
            self.sheets_tracker = get_global_sheets_tracker()
            self.job_scraper = create_job_scraper()
            
            logger.info("Job Application Agent initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize agent: {e}")
            raise
    
    def process_job(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a single job through the complete pipeline
        Returns processing result with status and metadata
        """
        
        job_id = job_data.get('job_id', 'unknown')
        job_title = job_data.get('job_title', 'Unknown Title')
        company_name = job_data.get('company_name', 'Unknown Company')
        
        logger.info(f"Processing job: {job_title} at {company_name} (ID: {job_id})")
        
        start_time = time.time()
        
        try:
            # Step 1: Check for duplicates
            if self.job_counter.is_duplicate_job(
                job_id, job_title, company_name, job_data.get('job_link', '')
            ):
                self.job_counter.record_duplicate_job(job_id, job_title, company_name)
                return {
                    'status': 'ignored',
                    'reason': 'duplicate',
                    'job_id': job_id,
                    'processing_time': time.time() - start_time
                }
            
            # Step 2: Role Detection (BEFORE location filtering)
            logger.info(f"Detecting role category for: {job_title}")
            role_category, role_variation, detection_metadata = self.role_detector.detect_role(
                job_title, job_data.get('job_description', '')
            )
            
            if role_category == "Unknown":
                self.job_counter.record_job_attempt(
                    job_id, job_title, company_name, 
                    job_data.get('job_link', ''), 'ignored', 'role=Unknown'
                )
                return {
                    'status': 'ignored',
                    'reason': 'role=Unknown',
                    'job_id': job_id,
                    'detection_metadata': detection_metadata,
                    'processing_time': time.time() - start_time
                }
            
            logger.info(f"Role detected: {role_category} -> {role_variation}")
            job_data.update({
                'role_category': role_category,
                'role_variation': role_variation
            })
            
            # Step 3: Location/Work Permit Filtering (AFTER role detection)
            logger.info("Checking location and work permit compatibility...")
            filter_decision = self.job_filter.should_ignore_job(
                job_title, company_name, 
                job_data.get('location', ''),
                job_data.get('job_description', '')
            )
            
            if filter_decision.should_stop:
                self.job_counter.record_job_attempt(
                    job_id, job_title, company_name,
                    job_data.get('job_link', ''), 'ignored', filter_decision.reason
                )
                
                # Log to sheets for tracking
                self.sheets_tracker.append_job(
                    job_id=job_id,
                    title=job_title,
                    company=company_name,
                    category=role_category,
                    variation=role_variation,
                    link=job_data.get('job_link', ''),
                    fit_score="",
                    status="ignored",
                    notes=filter_decision.reason,
                    folder_path=""
                )
                
                return {
                    'status': 'ignored',
                    'reason': filter_decision.reason,
                    'job_id': job_id,
                    'filter_details': filter_decision.details,
                    'processing_time': time.time() - start_time
                }
            
            logger.info("Job passed location/work permit filter")
            
            # Step 4: Load Base Resume
            logger.info(f"Loading base resume for {role_category}...")
            try:
                base_resume_path, base_resume_text = self.storage_service.load_base_resume(role_category)
            except FileNotFoundError:
                error_msg = f"Base resume not found for category: {role_category}"
                logger.error(error_msg)
                self.job_counter.record_job_attempt(
                    job_id, job_title, company_name,
                    job_data.get('job_link', ''), 'ignored', 'no_base_resume'
                )
                return {
                    'status': 'error',
                    'reason': 'no_base_resume',
                    'job_id': job_id,
                    'error': error_msg,
                    'processing_time': time.time() - start_time
                }
            
            # Step 5: Tailoring
            logger.info("Tailoring resume and generating cover letter...")
            tailored_resume_text, tailored_cover_letter_text, tailoring_metadata = self.tailoring_service.tailor_application(
                job_description=job_data.get('job_description', ''),
                base_resume_text=base_resume_text,
                role_category=role_category,
                company_name=company_name,
                company_address=job_data.get('company_address')
            )
            
            # Save debug data if enabled
            if settings.SAVE_DEBUG_DATA:
                self.storage_service.save_debug_data(job_id, 'tailoring_metadata', tailoring_metadata)
                self.storage_service.save_debug_data(job_id, 'base_resume', base_resume_text)
            
            # Step 6: Fit Scoring (AFTER tailoring)
            logger.info("Scoring job fit...")
            scoring_result = self.scoring_service.score_job_fit(
                job_description=job_data.get('job_description', ''),
                tailored_resume_text=tailored_resume_text,
                job_title=job_title,
                company_name=company_name
            )
            
            fit_score = scoring_result.get('score', 0)
            
            if fit_score < settings.FIT_SCORE_THRESHOLD:
                logger.info(f"Job fit score {fit_score:.1f} below threshold {settings.FIT_SCORE_THRESHOLD}")
                
                self.job_counter.record_job_attempt(
                    job_id, job_title, company_name,
                    job_data.get('job_link', ''), 'ignored', 'fit<8.5'
                )
                
                # Log to sheets
                self.sheets_tracker.append_job(
                    job_id=job_id,
                    title=job_title,
                    company=company_name,
                    category=role_category,
                    variation=role_variation,
                    link=job_data.get('job_link', ''),
                    fit_score=fit_score,
                    status="ignored",
                    notes="fit<8.5",
                    folder_path=""
                )
                
                return {
                    'status': 'ignored',
                    'reason': 'fit<8.5',
                    'job_id': job_id,
                    'fit_score': fit_score,
                    'scoring_result': scoring_result,
                    'processing_time': time.time() - start_time
                }
            
            logger.info(f"Job fit score {fit_score:.1f} meets threshold - proceeding with application")
            
            # Step 7: Document Generation & Storage
            logger.info("Generating and saving application documents...")
            
            # Update job data with all processing results
            complete_job_data = {
                **job_data,
                'tailored_resume_text': tailored_resume_text,
                'tailored_cover_letter_text': tailored_cover_letter_text,
                'fit_score': fit_score,
                'fit_analysis': scoring_result,
                'status': 'ready_to_apply',
                'processing_metadata': {
                    'processed_date': datetime.now().isoformat(),
                    'processing_time_seconds': time.time() - start_time,
                    'storage_mode': settings.STORAGE_MODE,
                    'agent_version': '1.0.0'
                }
            }
            
            # Save application documents
            storage_path, file_paths = self.storage_service.save_job_application(
                company_name=company_name,
                role_category=role_category,
                job_id=job_id,
                tailored_resume_text=tailored_resume_text,
                tailored_cover_letter_text=tailored_cover_letter_text,
                job_data=complete_job_data
            )
            
            # Step 8: Tracking & Logging
            logger.info("Recording successful application...")
            
            # Record in job counter
            self.job_counter.record_job_attempt(
                job_id, job_title, company_name,
                job_data.get('job_link', ''), 'ready_to_apply', None
            )
            
            # Log to Google Sheets
            self.sheets_tracker.append_job(
                job_id=job_id,
                title=job_title,
                company=company_name,
                category=role_category,
                variation=role_variation,
                link=job_data.get('job_link', ''),
                fit_score=fit_score,
                status="ready_to_apply",
                notes="",
                folder_path=storage_path
            )
            
            processing_time = time.time() - start_time
            logger.info(f"Successfully processed job application in {processing_time:.2f}s")
            
            return {
                'status': 'ready_to_apply',
                'job_id': job_id,
                'fit_score': fit_score,
                'storage_path': storage_path,
                'file_paths': file_paths,
                'processing_time': processing_time,
                'role_category': role_category,
                'role_variation': role_variation
            }
            
        except Exception as e:
            logger.error(f"Error processing job {job_id}: {e}", exc_info=True)
            
            # Record the error
            self.job_counter.record_job_attempt(
                job_id, job_title, company_name,
                job_data.get('job_link', ''), 'error', str(e)[:100]
            )
            
            return {
                'status': 'error',
                'job_id': job_id,
                'error': str(e),
                'processing_time': time.time() - start_time
            }
    
    def batch_process_jobs(self, max_jobs: Optional[int] = None) -> Dict[str, Any]:
        """
        Process multiple jobs from configured sources
        Returns batch processing summary
        """
        
        max_jobs = max_jobs or settings.MAX_JOBS_PER_RUN
        logger.info(f"Starting batch job processing (max {max_jobs} successful applications)")
        
        batch_start_time = time.time()
        processed_jobs = []
        successful_applications = 0
        
        try:
            # Scrape jobs from configured sources
            logger.info("Scraping jobs from configured sources...")
            scraped_jobs = self.job_scraper.scrape_jobs_from_sources()
            
            if not scraped_jobs:
                logger.warning("No jobs found from scraping sources")
                return {
                    'status': 'completed',
                    'total_scraped': 0,
                    'total_processed': 0,
                    'successful_applications': 0,
                    'processing_time': time.time() - batch_start_time
                }
            
            logger.info(f"Found {len(scraped_jobs)} jobs to process")
            
            # Process each job
            for i, job_data in enumerate(scraped_jobs):
                # Check if we should continue processing
                if not self.job_counter.can_process_more_jobs():
                    logger.info(f"Reached maximum applications limit ({max_jobs})")
                    break
                
                if not self.job_counter.should_continue_scraping():
                    logger.info("Reached scraping limits")
                    break
                
                logger.info(f"Processing job {i+1}/{len(scraped_jobs)}")
                
                # Process the job
                result = self.process_job(job_data)
                processed_jobs.append(result)
                
                if result['status'] == 'ready_to_apply':
                    successful_applications += 1
                
                # Update counters
                self.job_counter.increment_processed()
                
                # Small delay between jobs to be respectful
                time.sleep(1)
            
            # Generate summary
            batch_processing_time = time.time() - batch_start_time
            
            summary = {
                'status': 'completed',
                'total_scraped': len(scraped_jobs),
                'total_processed': len(processed_jobs),
                'successful_applications': successful_applications,
                'processing_time': batch_processing_time,
                'session_summary': self.job_counter.get_session_summary(),
                'job_results': processed_jobs
            }
            
            logger.info(f"Batch processing completed: {successful_applications} successful applications "
                       f"from {len(processed_jobs)} processed jobs in {batch_processing_time:.2f}s")
            
            return summary
            
        except Exception as e:
            logger.error(f"Error in batch processing: {e}", exc_info=True)
            return {
                'status': 'error',
                'error': str(e),
                'processing_time': time.time() - batch_start_time,
                'processed_jobs': processed_jobs
            }
        finally:
            # End the session
            self.job_counter.end_session()
    
    def process_single_job_from_input(self, job_input: Dict[str, str]) -> Dict[str, Any]:
        """Process a single job from manual input"""
        
        # Convert input to job data format
        job_data = {
            'job_id': f"manual_{int(time.time())}",
            'job_title': job_input.get('title', 'Manual Job'),
            'company_name': job_input.get('company', 'Manual Company'),
            'job_link': job_input.get('link', ''),
            'location': job_input.get('location', 'Unknown'),
            'job_description': job_input.get('description', ''),
            'country': job_input.get('country', 'Unknown')
        }
        
        return self.process_job(job_data)
    
    def validate_setup(self) -> Dict[str, List[str]]:
        """Validate complete system setup"""
        
        logger.info("Validating system setup...")
        
        validation_results = {
            'configuration': [],
            'storage': [],
            'ai_services': [],
            'google_services': [],
            'prompts': [],
            'base_resumes': []
        }
        
        try:
            # Validate configuration
            config_errors = settings.validate_config()
            validation_results['configuration'] = config_errors
            
            # Validate storage
            storage_errors = self.storage_service.validate_storage_setup()
            validation_results['storage'] = storage_errors
            
            # Validate AI services
            ai_errors = self.scoring_service.gpt_service.validate_api_setup()
            validation_results['ai_services'] = ai_errors
            
            # Validate Google services
            try:
                sheets_errors = self.sheets_tracker.validate_setup()
                validation_results['google_services'] = sheets_errors
            except Exception as e:
                validation_results['google_services'] = [f"Sheets validation failed: {e}"]
            
            # Validate prompts
            from services.tailoring_service import validate_prompt_template
            from services.scoring_service import validate_scoring_setup
            
            prompt_errors = validate_prompt_template()
            scoring_errors = validate_scoring_setup()
            validation_results['prompts'] = prompt_errors + scoring_errors
            
            # Validate base resumes
            available_resumes = self.storage_service.get_available_base_resumes()
            if not available_resumes:
                validation_results['base_resumes'] = ["No base resume templates found"]
            else:
                validation_results['base_resumes'] = [f"Found {len(available_resumes)} base resume templates"]
            
        except Exception as e:
            logger.error(f"Error during validation: {e}")
            validation_results['system'] = [f"Validation failed: {e}"]
        
        # Summary
        total_issues = sum(len(issues) for issues in validation_results.values())
        if total_issues == 0:
            logger.info("System validation passed - all components ready")
        else:
            logger.warning(f"System validation found {total_issues} issues")
        
        return validation_results
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get current system status and statistics"""
        
        return {
            'agent_version': '1.0.0',
            'configuration': {
                'storage_mode': settings.STORAGE_MODE,
                'max_jobs_per_run': settings.MAX_JOBS_PER_RUN,
                'fit_threshold': settings.FIT_SCORE_THRESHOLD,
                'applicant_country': settings.APPLICANT_COUNTRY
            },
            'session_summary': self.job_counter.get_session_summary(),
            'storage_stats': self.storage_service.get_storage_stats(),
            'available_roles': self.role_detector.get_role_categories(),
            'available_base_resumes': self.storage_service.get_available_base_resumes()
        }


def create_argument_parser() -> argparse.ArgumentParser:
    """Create command line argument parser"""
    
    parser = argparse.ArgumentParser(
        description="Job Application Agent - Automated job application with AI tailoring",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --batch                          # Process jobs from configured sources
  python main.py --url "https://..."             # Process single job from URL
  python main.py --validate                      # Validate system setup
  python main.py --status                        # Show system status
  python main.py --jd-file job.txt --title "..." --company "..." --link "..."
        """
    )
    
    # Main operation modes
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--batch', action='store_true',
                      help='Process jobs in batch mode from configured sources')
    group.add_argument('--url', type=str,
                      help='Process single job from URL')
    group.add_argument('--validate', action='store_true',
                      help='Validate system setup and configuration')
    group.add_argument('--status', action='store_true',
                      help='Show current system status')
    
    # Manual job input options
    parser.add_argument('--jd-file', type=str,
                       help='Path to job description text file')
    parser.add_argument('--title', type=str,
                       help='Job title (required with --jd-file)')
    parser.add_argument('--company', type=str,
                       help='Company name (required with --jd-file)')
    parser.add_argument('--link', type=str,
                       help='Job posting URL (optional with --jd-file)')
    parser.add_argument('--location', type=str, default='Unknown',
                       help='Job location (optional with --jd-file)')
    
    # Processing options
    parser.add_argument('--max-jobs', type=int,
                       help='Maximum number of successful applications (overrides config)')
    parser.add_argument('--debug', action='store_true',
                       help='Enable debug logging')
    parser.add_argument('--quiet', action='store_true',
                       help='Minimal output (only results)')
    
    return parser


def main():
    """Main entry point"""
    
    parser = create_argument_parser()
    args = parser.parse_args()
    
    # Configure logging level
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    elif args.quiet:
        logging.getLogger().setLevel(logging.WARNING)
    
    try:
        # Initialize agent
        if not args.validate and not args.status:
            logger.info("Starting Job Application Agent...")
        
        agent = JobApplicationAgent()
        
        # Handle different operation modes
        if args.validate:
            # Validation mode
            print("Validating system setup...")
            validation_results = agent.validate_setup()
            
            # Print results
            all_good = True
            for component, issues in validation_results.items():
                if issues and any(issue for issue in issues if not issue.startswith("Found")):
                    all_good = False
                    print(f"\n❌ {component.title()}:")
                    for issue in issues:
                        if not issue.startswith("Found"):
                            print(f"  - {issue}")
                else:
                    print(f"✅ {component.title()}: OK")
            
            if all_good:
                print("\n🎉 System validation passed! Ready to process jobs.")
            else:
                print("\n⚠️  Please fix the issues above before running the agent.")
                sys.exit(1)
        
        elif args.status:
            # Status mode
            status = agent.get_system_status()
            print("\n📊 Job Application Agent Status")
            print("=" * 40)
            print(f"Storage Mode: {status['configuration']['storage_mode']}")
            print(f"Max Jobs per Run: {status['configuration']['max_jobs_per_run']}")
            print(f"Fit Threshold: {status['configuration']['fit_threshold']}")
            print(f"Applicant Country: {status['configuration']['applicant_country']}")
            print(f"Available Roles: {len(status['available_roles'])}")
            print(f"Base Resumes: {len(status['available_base_resumes'])}")
            
            session = status['session_summary']
            print(f"\nCurrent Session:")
            print(f"  Successful Applications: {session['successful_applications']}")
            print(f"  Remaining Slots: {session['remaining_slots']}")
            print(f"  Can Process More: {session['can_process_more']}")
        
        elif args.batch:
            # Batch processing mode
            max_jobs = args.max_jobs or settings.MAX_JOBS_PER_RUN
            result = agent.batch_process_jobs(max_jobs)
            
            # Print summary
            print(f"\n📋 Batch Processing Summary")
            print("=" * 40)
            print(f"Status: {result['status']}")
            print(f"Jobs Scraped: {result.get('total_scraped', 0)}")
            print(f"Jobs Processed: {result.get('total_processed', 0)}")
            print(f"Successful Applications: {result.get('successful_applications', 0)}")
            print(f"Processing Time: {result.get('processing_time', 0):.2f}s")
            
            if result['status'] == 'error':
                print(f"Error: {result.get('error', 'Unknown error')}")
                sys.exit(1)
        
        elif args.url:
            # Single URL processing
            job_input = {
                'link': args.url,
                'title': 'URL Job',
                'company': 'Unknown',
                'description': f'Job from URL: {args.url}'
            }
            
            result = agent.process_single_job_from_input(job_input)
            
            # Print result
            print(f"\n🎯 Job Processing Result")
            print("=" * 30)
            print(f"Status: {result['status']}")
            print(f"Job ID: {result['job_id']}")
            
            if result['status'] == 'ready_to_apply':
                print(f"Fit Score: {result['fit_score']:.1f}")
                print(f"Storage Path: {result['storage_path']}")
                print("✅ Application ready!")
            elif result['status'] == 'ignored':
                print(f"Reason: {result['reason']}")
                print("⚠️  Job ignored")
            else:
                print(f"Error: {result.get('error', 'Unknown error')}")
                print("❌ Processing failed")
        
        elif args.jd_file:
            # Manual job description file processing
            if not args.title or not args.company:
                print("Error: --title and --company are required when using --jd-file")
                sys.exit(1)
            
            # Read job description
            jd_file = Path(args.jd_file)
            if not jd_file.exists():
                print(f"Error: Job description file not found: {jd_file}")
                sys.exit(1)
            
            with open(jd_file, 'r', encoding='utf-8') as f:
                job_description = f.read()
            
            job_input = {
                'title': args.title,
                'company': args.company,
                'link': args.link or '',
                'location': args.location,
                'description': job_description
            }
            
            result = agent.process_single_job_from_input(job_input)
            
            # Print result (same as URL processing)
            print(f"\n🎯 Job Processing Result")
            print("=" * 30)
            print(f"Status: {result['status']}")
            print(f"Job ID: {result['job_id']}")
            
            if result['status'] == 'ready_to_apply':
                print(f"Fit Score: {result['fit_score']:.1f}")
                print(f"Storage Path: {result['storage_path']}")
                print("✅ Application ready!")
            elif result['status'] == 'ignored':
                print(f"Reason: {result['reason']}")
                print("⚠️  Job ignored")
            else:
                print(f"Error: {result.get('error', 'Unknown error')}")
                print("❌ Processing failed")
    
    except KeyboardInterrupt:
        logger.info("Process interrupted by user")
        print("\n⏹️  Process stopped by user")
        sys.exit(0)
    
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        print(f"\n❌ Unexpected error: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
