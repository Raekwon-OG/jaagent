"""
Local file management for job application documents
"""
import os
import json
import logging
import shutil
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from datetime import datetime
from config import settings

logger = logging.getLogger(__name__)

class LocalFileManager:
    """Manages local file operations for job applications"""
    
    def __init__(self):
        self.applications_dir = Path(settings.APPLICATIONS_DIR)
        self.base_resumes_dir = Path(settings.BASE_RESUMES_DIR)
        self.debug_dir = Path(settings.DEBUG_DATA_DIR) if settings.SAVE_DEBUG_DATA else None
        
        # Ensure directories exist
        self._ensure_directories()
    
    def _ensure_directories(self):
        """Create necessary directories if they don't exist"""
        directories = [self.applications_dir, self.base_resumes_dir]
        
        if self.debug_dir:
            directories.append(self.debug_dir)
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Ensured directory exists: {directory}")
    
    def create_job_folder(self, company_name: str, role_category: str, job_id: str) -> Path:
        """Create a folder for a specific job application"""
        
        # Sanitize folder name
        folder_name = self._sanitize_folder_name(f"{company_name}_{role_category}_{job_id}")
        job_folder = self.applications_dir / folder_name
        
        try:
            job_folder.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created job folder: {job_folder}")
            return job_folder
            
        except Exception as e:
            logger.error(f"Error creating job folder: {e}")
            raise
    
    def _sanitize_folder_name(self, name: str) -> str:
        """Sanitize folder name to be filesystem-safe"""
        # Replace invalid characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            name = name.replace(char, '_')
        
        # Replace spaces and multiple underscores
        name = name.replace(' ', '_')
        name = '_'.join(filter(None, name.split('_')))  # Remove empty parts
        
        # Limit length
        if len(name) > 100:
            name = name[:100]
        
        return name
    
    def save_job_details(self, job_folder: Path, job_data: Dict) -> Path:
        """Save job details as JSON file"""
        
        job_details_file = job_folder / settings.JOB_DETAILS_FILENAME
        
        try:
            # Add file metadata
            job_data_with_metadata = {
                **job_data,
                'file_metadata': {
                    'created_at': datetime.now().isoformat(),
                    'storage_mode': 'local',
                    'folder_path': str(job_folder),
                    'agent_version': '1.0.0'
                }
            }
            
            with open(job_details_file, 'w', encoding='utf-8') as f:
                json.dump(job_data_with_metadata, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Saved job details: {job_details_file}")
            return job_details_file
            
        except Exception as e:
            logger.error(f"Error saving job details: {e}")
            raise
    
    def save_text_file(self, job_folder: Path, filename: str, content: str) -> Path:
        """Save text content to file"""
        
        file_path = job_folder / filename
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            logger.debug(f"Saved text file: {file_path}")
            return file_path
            
        except Exception as e:
            logger.error(f"Error saving text file {filename}: {e}")
            raise
    
    def load_base_resume(self, role_category: str) -> Tuple[Path, str]:
        """Load base resume for a role category"""
        
        base_resume_file = self.base_resumes_dir / f"{role_category}.docx"
        
        if not base_resume_file.exists():
            error_msg = f"Base resume not found for role category: {role_category}"
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)
        
        try:
            # Extract text from DOCX for processing
            from utils.docx_tools import DocxProcessor
            docx_processor = DocxProcessor()
            resume_text = docx_processor.extract_text_from_docx(base_resume_file)
            
            logger.info(f"Loaded base resume for {role_category}: {base_resume_file}")
            return base_resume_file, resume_text
            
        except Exception as e:
            logger.error(f"Error loading base resume: {e}")
            raise
    
    def get_available_base_resumes(self) -> List[str]:
        """Get list of available base resume categories"""
        
        categories = []
        
        try:
            for file_path in self.base_resumes_dir.glob("*.docx"):
                # Extract category name from filename
                category = file_path.stem
                categories.append(category)
            
            logger.info(f"Found {len(categories)} base resume categories")
            return sorted(categories)
            
        except Exception as e:
            logger.error(f"Error listing base resumes: {e}")
            return []
    
    def save_debug_data(self, job_id: str, data_type: str, data: any) -> Optional[Path]:
        """Save debug data for analysis"""
        
        if not settings.SAVE_DEBUG_DATA or not self.debug_dir:
            return None
        
        try:
            # Create debug subfolder for this job
            job_debug_dir = self.debug_dir / job_id
            job_debug_dir.mkdir(parents=True, exist_ok=True)
            
            # Save data based on type
            if isinstance(data, (dict, list)):
                debug_file = job_debug_dir / f"{data_type}.json"
                with open(debug_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            else:
                debug_file = job_debug_dir / f"{data_type}.txt"
                with open(debug_file, 'w', encoding='utf-8') as f:
                    f.write(str(data))
            
            logger.debug(f"Saved debug data: {debug_file}")
            return debug_file
            
        except Exception as e:
            logger.error(f"Error saving debug data: {e}")
            return None
    
    def cleanup_old_applications(self, days_to_keep: int = 30) -> int:
        """Clean up old application folders"""
        
        if not self.applications_dir.exists():
            return 0
        
        cutoff_date = datetime.now().timestamp() - (days_to_keep * 24 * 60 * 60)
        removed_count = 0
        
        try:
            for folder in self.applications_dir.iterdir():
                if folder.is_dir():
                    # Check folder modification time
                    if folder.stat().st_mtime < cutoff_date:
                        shutil.rmtree(folder)
                        removed_count += 1
                        logger.debug(f"Removed old application folder: {folder}")
            
            if removed_count > 0:
                logger.info(f"Cleaned up {removed_count} old application folders")
            
            return removed_count
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
            return 0
    
    def get_application_folders(self) -> List[Dict[str, any]]:
        """Get list of existing application folders with metadata"""
        
        folders = []
        
        try:
            if not self.applications_dir.exists():
                return folders
            
            for folder in self.applications_dir.iterdir():
                if folder.is_dir():
                    # Try to load job details
                    job_details_file = folder / settings.JOB_DETAILS_FILENAME
                    
                    folder_info = {
                        'folder_name': folder.name,
                        'folder_path': str(folder),
                        'created_time': datetime.fromtimestamp(folder.stat().st_ctime),
                        'modified_time': datetime.fromtimestamp(folder.stat().st_mtime),
                        'has_job_details': job_details_file.exists()
                    }
                    
                    # Add job details if available
                    if job_details_file.exists():
                        try:
                            with open(job_details_file, 'r', encoding='utf-8') as f:
                                job_data = json.load(f)
                                folder_info.update({
                                    'job_title': job_data.get('job_title', 'Unknown'),
                                    'company_name': job_data.get('company_name', 'Unknown'),
                                    'role_category': job_data.get('role_category', 'Unknown'),
                                    'status': job_data.get('status', 'Unknown')
                                })
                        except Exception as e:
                            logger.warning(f"Error reading job details from {job_details_file}: {e}")
                    
                    folders.append(folder_info)
            
            # Sort by creation time (newest first)
            folders.sort(key=lambda x: x['created_time'], reverse=True)
            
        except Exception as e:
            logger.error(f"Error listing application folders: {e}")
        
        return folders
    
    def validate_storage_setup(self) -> List[str]:
        """Validate local storage setup and return any issues"""
        
        issues = []
        
        # Check if directories exist and are writable
        directories_to_check = [
            (self.applications_dir, "Applications directory"),
            (self.base_resumes_dir, "Base resumes directory")
        ]
        
        if self.debug_dir:
            directories_to_check.append((self.debug_dir, "Debug directory"))
        
        for directory, description in directories_to_check:
            if not directory.exists():
                try:
                    directory.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    issues.append(f"{description} cannot be created: {e}")
                    continue
            
            # Test write permissions
            test_file = directory / ".write_test"
            try:
                test_file.write_text("test")
                test_file.unlink()
            except Exception as e:
                issues.append(f"{description} is not writable: {e}")
        
        # Check for base resumes
        available_resumes = self.get_available_base_resumes()
        if not available_resumes:
            issues.append("No base resume templates found in base_resumes directory")
        
        # Check disk space (basic check)
        try:
            statvfs = os.statvfs(self.applications_dir)
            free_space_gb = (statvfs.f_frsize * statvfs.f_bavail) / (1024**3)
            if free_space_gb < 1:  # Less than 1GB free
                issues.append(f"Low disk space: {free_space_gb:.2f} GB available")
        except Exception:
            # statvfs not available on all systems
            pass
        
        return issues
    
    def get_storage_stats(self) -> Dict[str, any]:
        """Get storage usage statistics"""
        
        stats = {
            'total_applications': 0,
            'total_files': 0,
            'total_size_mb': 0,
            'available_base_resumes': len(self.get_available_base_resumes()),
            'storage_mode': 'local',
            'applications_directory': str(self.applications_dir)
        }
        
        try:
            if self.applications_dir.exists():
                total_size = 0
                total_files = 0
                
                for folder in self.applications_dir.iterdir():
                    if folder.is_dir():
                        stats['total_applications'] += 1
                        
                        for file_path in folder.rglob('*'):
                            if file_path.is_file():
                                total_files += 1
                                total_size += file_path.stat().st_size
                
                stats['total_files'] = total_files
                stats['total_size_mb'] = round(total_size / (1024 * 1024), 2)
        
        except Exception as e:
            logger.error(f"Error calculating storage stats: {e}")
        
        return stats


# Factory function for easy access
def create_file_manager() -> LocalFileManager:
    """Create a configured file manager instance"""
    return LocalFileManager()


# Global file manager instance
_global_file_manager: Optional[LocalFileManager] = None

def get_global_file_manager() -> LocalFileManager:
    """Get or create the global file manager instance"""
    global _global_file_manager
    if _global_file_manager is None:
        _global_file_manager = create_file_manager()
    return _global_file_manager