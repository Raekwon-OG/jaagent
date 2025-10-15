"""
Unified storage service that abstracts local and cloud storage
"""
import json
import logging
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
from datetime import datetime

from config import settings
from utils.file_manager import LocalFileManager, get_global_file_manager
from utils.drive_manager import GoogleDriveManager, get_global_drive_manager, validate_drive_dependencies
from utils.docx_tools import create_documents_from_text

logger = logging.getLogger(__name__)

class StorageService:
    """Unified interface for local and cloud storage operations"""
    
    def __init__(self, storage_mode: Optional[str] = None):
        self.storage_mode = storage_mode or settings.STORAGE_MODE
        
        # Initialize appropriate storage manager
        if self.storage_mode == "local":
            self.file_manager = get_global_file_manager()
            self.drive_manager = None
        elif self.storage_mode == "cloud":
            # Validate Google Drive dependencies first
            drive_issues = validate_drive_dependencies()
            if drive_issues:
                logger.error(f"Google Drive not available: {drive_issues}")
                raise RuntimeError(f"Cannot use cloud storage: {', '.join(drive_issues)}")
            
            self.drive_manager = get_global_drive_manager()
            self.file_manager = get_global_file_manager()  # Still need for base resumes
        else:
            raise ValueError(f"Invalid storage mode: {self.storage_mode}")
        
        logger.info(f"Storage service initialized in {self.storage_mode} mode")
    
    def save_job_application(self, company_name: str, role_category: str, job_id: str,
                           tailored_resume_text: str, tailored_cover_letter_text: str,
                           job_data: Dict[str, Any]) -> Tuple[str, Dict[str, str]]:
        """
        Save complete job application with documents and metadata
        Returns: (storage_path, file_paths_dict)
        """
        
        logger.info(f"Saving job application for {company_name} - {role_category} ({job_id})")
        
        try:
            if self.storage_mode == "local":
                return self._save_local_application(
                    company_name, role_category, job_id,
                    tailored_resume_text, tailored_cover_letter_text, job_data
                )
            else:  # cloud mode
                return self._save_cloud_application(
                    company_name, role_category, job_id,
                    tailored_resume_text, tailored_cover_letter_text, job_data
                )
                
        except Exception as e:
            logger.error(f"Error saving job application: {e}")
            raise
    
    def _save_local_application(self, company_name: str, role_category: str, job_id: str,
                              tailored_resume_text: str, tailored_cover_letter_text: str,
                              job_data: Dict[str, Any]) -> Tuple[str, Dict[str, str]]:
        """Save application to local storage"""
        
        # Create job folder
        job_folder = self.file_manager.create_job_folder(company_name, role_category, job_id)
        
        # Create documents
        document_paths = create_documents_from_text(
            job_folder, tailored_resume_text, tailored_cover_letter_text
        )
        
        # Save job details JSON
        job_details_path = self.file_manager.save_job_details(job_folder, job_data)
        document_paths['job_details'] = job_details_path
        
        # Convert paths to strings for return
        file_paths_dict = {key: str(path) for key, path in document_paths.items()}
        
        logger.info(f"Saved {len(document_paths)} files to local storage: {job_folder}")
        
        return str(job_folder), file_paths_dict
    
    def _save_cloud_application(self, company_name: str, role_category: str, job_id: str,
                              tailored_resume_text: str, tailored_cover_letter_text: str,
                              job_data: Dict[str, Any]) -> Tuple[str, Dict[str, str]]:
        """Save application to Google Drive"""
        
        # Create documents in temporary local location first
        import tempfile
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_folder = Path(temp_dir)
            
            # Create documents locally
            document_paths = create_documents_from_text(
                temp_folder, tailored_resume_text, tailored_cover_letter_text
            )
            
            # Create job details file
            job_details_path = temp_folder / settings.JOB_DETAILS_FILENAME
            with open(job_details_path, 'w', encoding='utf-8') as f:
                json.dump(job_data, f, indent=2, ensure_ascii=False)
            
            # Upload to Google Drive
            folder_id = self.drive_manager.create_job_folder(company_name, role_category, job_id)
            
            uploaded_files = {}
            
            # Upload each document
            for doc_type, local_path in document_paths.items():
                file_id = self.drive_manager.upload_local_file(folder_id, local_path)
                uploaded_files[doc_type] = self.drive_manager.get_file_link(file_id)
            
            # Upload job details
            job_details_file_id = self.drive_manager.upload_local_file(folder_id, job_details_path)
            uploaded_files['job_details'] = self.drive_manager.get_file_link(job_details_file_id)
            
            folder_link = self.drive_manager.get_folder_link(folder_id)
            
            logger.info(f"Saved {len(uploaded_files)} files to Google Drive: {folder_link}")
            
            return folder_link, uploaded_files
    
    def load_base_resume(self, role_category: str) -> Tuple[str, str]:
        """Load base resume for role category (always from local storage)"""
        
        try:
            base_resume_path, resume_text = self.file_manager.load_base_resume(role_category)
            logger.info(f"Loaded base resume for {role_category}")
            return str(base_resume_path), resume_text
            
        except Exception as e:
            logger.error(f"Error loading base resume for {role_category}: {e}")
            raise
    
    def get_available_base_resumes(self) -> List[str]:
        """Get list of available base resume categories"""
        return self.file_manager.get_available_base_resumes()
    
    def list_applications(self) -> List[Dict[str, Any]]:
        """List all job applications"""
        
        try:
            if self.storage_mode == "local":
                return self.file_manager.get_application_folders()
            else:  # cloud mode
                return self.drive_manager.list_job_folders()
                
        except Exception as e:
            logger.error(f"Error listing applications: {e}")
            return []
    
    def get_storage_stats(self) -> Dict[str, Any]:
        """Get storage usage statistics"""
        
        try:
            if self.storage_mode == "local":
                return self.file_manager.get_storage_stats()
            else:  # cloud mode
                return self.drive_manager.get_storage_stats()
                
        except Exception as e:
            logger.error(f"Error getting storage stats: {e}")
            return {'error': str(e)}
    
    def cleanup_old_applications(self, days_to_keep: int = 30) -> int:
        """Clean up old applications"""
        
        try:
            if self.storage_mode == "local":
                return self.file_manager.cleanup_old_applications(days_to_keep)
            else:  # cloud mode
                return self.drive_manager.cleanup_old_folders(days_to_keep)
                
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
            return 0
    
    def validate_storage_setup(self) -> List[str]:
        """Validate storage setup and return any issues"""
        
        issues = []
        
        try:
            if self.storage_mode == "local":
                issues.extend(self.file_manager.validate_storage_setup())
            else:  # cloud mode
                issues.extend(self.drive_manager.validate_drive_setup())
                # Also validate local setup for base resumes
                local_issues = self.file_manager.validate_storage_setup()
                # Filter out application directory issues since we use cloud for that
                filtered_local_issues = [
                    issue for issue in local_issues 
                    if 'Applications directory' not in issue
                ]
                issues.extend(filtered_local_issues)
                
        except Exception as e:
            issues.append(f"Storage validation failed: {e}")
        
        return issues
    
    def save_debug_data(self, job_id: str, data_type: str, data: Any) -> bool:
        """Save debug data (always local)"""
        
        try:
            if settings.SAVE_DEBUG_DATA:
                result = self.file_manager.save_debug_data(job_id, data_type, data)
                return result is not None
            return False
            
        except Exception as e:
            logger.error(f"Error saving debug data: {e}")
            return False
    
    def switch_storage_mode(self, new_mode: str) -> bool:
        """Switch storage mode (for testing or user preference)"""
        
        if new_mode not in ["local", "cloud"]:
            logger.error(f"Invalid storage mode: {new_mode}")
            return False
        
        try:
            # Validate new mode is available
            if new_mode == "cloud":
                drive_issues = validate_drive_dependencies()
                if drive_issues:
                    logger.error(f"Cannot switch to cloud mode: {drive_issues}")
                    return False
                
                # Test Google Drive connection
                test_manager = GoogleDriveManager()
                test_issues = test_manager.validate_drive_setup()
                if test_issues:
                    logger.error(f"Google Drive setup issues: {test_issues}")
                    return False
            
            # Switch mode
            old_mode = self.storage_mode
            self.storage_mode = new_mode
            
            # Reinitialize managers
            if new_mode == "local":
                self.drive_manager = None
            else:
                self.drive_manager = get_global_drive_manager()
            
            logger.info(f"Switched storage mode from {old_mode} to {new_mode}")
            return True
            
        except Exception as e:
            logger.error(f"Error switching storage mode: {e}")
            return False
    
    def get_application_link(self, storage_path: str) -> str:
        """Get shareable link for application (cloud mode only)"""
        
        if self.storage_mode == "cloud" and self.drive_manager:
            # storage_path is already a Drive folder link in cloud mode
            return storage_path
        else:
            # Return local file path for local mode
            return f"file://{storage_path}"
    
    def export_applications_list(self, output_path: Path) -> bool:
        """Export list of applications to CSV/JSON for analysis"""
        
        try:
            applications = self.list_applications()
            
            if output_path.suffix.lower() == '.json':
                # Export as JSON
                export_data = {
                    'export_date': datetime.now().isoformat(),
                    'storage_mode': self.storage_mode,
                    'total_applications': len(applications),
                    'applications': applications
                }
                
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(export_data, f, indent=2, ensure_ascii=False, default=str)
            
            else:
                # Export as CSV
                import csv
                
                if not applications:
                    return False
                
                # Get all possible field names
                all_fields = set()
                for app in applications:
                    all_fields.update(app.keys())
                
                fieldnames = sorted(all_fields)
                
                with open(output_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    
                    for app in applications:
                        # Convert complex fields to strings
                        row = {}
                        for field in fieldnames:
                            value = app.get(field, '')
                            if isinstance(value, (dict, list)):
                                row[field] = json.dumps(value)
                            else:
                                row[field] = str(value) if value is not None else ''
                        writer.writerow(row)
            
            logger.info(f"Exported {len(applications)} applications to {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error exporting applications: {e}")
            return False


class StorageFactory:
    """Factory for creating storage service instances"""
    
    @staticmethod
    def create_storage_service(mode: Optional[str] = None) -> StorageService:
        """Create storage service with specified mode"""
        return StorageService(mode)
    
    @staticmethod
    def get_available_storage_modes() -> List[str]:
        """Get list of available storage modes"""
        modes = ["local"]
        
        # Check if cloud storage is available
        drive_issues = validate_drive_dependencies()
        if not drive_issues:
            try:
                # Test if credentials are available
                GoogleDriveManager()
                modes.append("cloud")
            except Exception:
                pass  # Cloud mode not available
        
        return modes
    
    @staticmethod
    def validate_all_storage_modes() -> Dict[str, List[str]]:
        """Validate all available storage modes"""
        validation_results = {}
        
        # Test local storage
        try:
            local_service = StorageService("local")
            validation_results["local"] = local_service.validate_storage_setup()
        except Exception as e:
            validation_results["local"] = [f"Local storage initialization failed: {e}"]
        
        # Test cloud storage
        drive_issues = validate_drive_dependencies()
        if drive_issues:
            validation_results["cloud"] = drive_issues
        else:
            try:
                cloud_service = StorageService("cloud")
                validation_results["cloud"] = cloud_service.validate_storage_setup()
            except Exception as e:
                validation_results["cloud"] = [f"Cloud storage initialization failed: {e}"]
        
        return validation_results


# Global storage service instance
_global_storage_service: Optional[StorageService] = None

def get_global_storage_service() -> StorageService:
    """Get or create the global storage service instance"""
    global _global_storage_service
    if _global_storage_service is None:
        _global_storage_service = StorageService()
    return _global_storage_service

def reset_global_storage_service():
    """Reset global storage service (useful for testing)"""
    global _global_storage_service
    _global_storage_service = None


# Convenience functions for common operations
def save_job_application(company_name: str, role_category: str, job_id: str,
                        tailored_resume_text: str, tailored_cover_letter_text: str,
                        job_data: Dict[str, Any]) -> Tuple[str, Dict[str, str]]:
    """Quick function to save job application"""
    storage = get_global_storage_service()
    return storage.save_job_application(
        company_name, role_category, job_id,
        tailored_resume_text, tailored_cover_letter_text, job_data
    )

def load_base_resume(role_category: str) -> Tuple[str, str]:
    """Quick function to load base resume"""
    storage = get_global_storage_service()
    return storage.load_base_resume(role_category)

def validate_storage() -> List[str]:
    """Quick function to validate current storage setup"""
    storage = get_global_storage_service()
    return storage.validate_storage_setup()

def get_storage_mode() -> str:
    """Get current storage mode"""
    return settings.STORAGE_MODE

def switch_storage_mode(new_mode: str) -> bool:
    """Switch storage mode globally"""
    storage = get_global_storage_service()
    if storage.switch_storage_mode(new_mode):
        # Update settings
        settings.STORAGE_MODE = new_mode
        return True
    return False


# Storage mode context manager
class StorageModeContext:
    """Context manager for temporarily switching storage mode"""
    
    def __init__(self, temporary_mode: str):
        self.temporary_mode = temporary_mode
        self.original_mode = None
        self.storage_service = None
    
    def __enter__(self) -> StorageService:
        self.original_mode = get_storage_mode()
        self.storage_service = StorageService(self.temporary_mode)
        return self.storage_service
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        # Reset to original mode if it was changed
        if self.original_mode != self.temporary_mode:
            settings.STORAGE_MODE = self.original_mode


# Usage example:
# with StorageModeContext("cloud") as cloud_storage:
#     cloud_storage.save_job_application(...)