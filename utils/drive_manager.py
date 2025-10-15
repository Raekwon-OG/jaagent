"""
Google Drive management for cloud storage of job application documents
"""
import io
import json
import logging
import mimetypes
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
from datetime import datetime

try:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
    from google.auth.transport.requests import Request
    from google.oauth2.service_account import Credentials
    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False

from config import settings

logger = logging.getLogger(__name__)

class GoogleDriveManager:
    """Manages Google Drive operations for job applications"""
    
    def __init__(self):
        if not GOOGLE_AVAILABLE:
            raise ImportError("Google API client libraries not installed. Run: pip install google-api-python-client google-auth")
        
        self.credentials_file = Path(settings.DRIVE_CREDENTIALS_FILE)
        self.main_folder_name = settings.GOOGLE_DRIVE_FOLDER_NAME
        self.create_subfolders = settings.GOOGLE_DRIVE_SUBFOLDER_STRUCTURE
        
        self.service = None
        self.main_folder_id = None
        
        # Initialize connection
        self._initialize_drive_service()
        self._ensure_main_folder()
    
    def _initialize_drive_service(self):
        """Initialize Google Drive service with authentication"""
        
        if not self.credentials_file.exists():
            error_msg = f"Google Drive credentials file not found: {self.credentials_file}"
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)
        
        try:
            # Define the scopes
            scopes = ['https://www.googleapis.com/auth/drive.file']
            
            # Load credentials from service account file
            credentials = Credentials.from_service_account_file(
                str(self.credentials_file),
                scopes=scopes
            )
            
            # Build the service
            self.service = build('drive', 'v3', credentials=credentials)
            
            # Test connection
            self.service.about().get(fields="user").execute()
            logger.info("Successfully connected to Google Drive")
            
        except Exception as e:
            logger.error(f"Error initializing Google Drive service: {e}")
            raise
    
    def _ensure_main_folder(self):
        """Ensure the main job applications folder exists"""
        
        try:
            # Search for existing folder
            query = f"name='{self.main_folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            results = self.service.files().list(q=query, fields='files(id, name)').execute()
            
            folders = results.get('files', [])
            
            if folders:
                self.main_folder_id = folders[0]['id']
                logger.info(f"Found existing main folder: {self.main_folder_name}")
            else:
                # Create main folder
                folder_metadata = {
                    'name': self.main_folder_name,
                    'mimeType': 'application/vnd.google-apps.folder'
                }
                
                folder = self.service.files().create(body=folder_metadata, fields='id').execute()
                self.main_folder_id = folder['id']
                logger.info(f"Created main folder: {self.main_folder_name}")
            
        except Exception as e:
            logger.error(f"Error ensuring main folder: {e}")
            raise
    
    def create_job_folder(self, company_name: str, role_category: str, job_id: str) -> str:
        """Create a folder for a specific job application and return folder ID"""
        
        folder_name = self._sanitize_folder_name(f"{company_name}_{role_category}_{job_id}")
        
        try:
            # Check if folder already exists
            query = f"name='{folder_name}' and parents in '{self.main_folder_id}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            results = self.service.files().list(q=query, fields='files(id, name)').execute()
            
            folders = results.get('files', [])
            
            if folders:
                folder_id = folders[0]['id']
                logger.info(f"Found existing job folder: {folder_name}")
            else:
                # Create new folder
                folder_metadata = {
                    'name': folder_name,
                    'mimeType': 'application/vnd.google-apps.folder',
                    'parents': [self.main_folder_id]
                }
                
                folder = self.service.files().create(body=folder_metadata, fields='id').execute()
                folder_id = folder['id']
                logger.info(f"Created job folder: {folder_name}")
            
            return folder_id
            
        except Exception as e:
            logger.error(f"Error creating job folder: {e}")
            raise
    
    def _sanitize_folder_name(self, name: str) -> str:
        """Sanitize folder name for Google Drive"""
        # Google Drive has fewer restrictions than local filesystems
        # but we'll still clean up for consistency
        invalid_chars = '/\\<>:"|?*'
        for char in invalid_chars:
            name = name.replace(char, '_')
        
        name = name.replace('  ', ' ').strip()
        
        # Limit length
        if len(name) > 100:
            name = name[:100]
        
        return name
    
    def upload_file(self, folder_id: str, file_name: str, file_content: str, mime_type: str = None) -> str:
        """Upload a file to Google Drive and return file ID"""
        
        if mime_type is None:
            mime_type = mimetypes.guess_type(file_name)[0] or 'text/plain'
        
        try:
            # Create file metadata
            file_metadata = {
                'name': file_name,
                'parents': [folder_id]
            }
            
            # Create media upload
            if isinstance(file_content, str):
                media = MediaFileUpload(
                    io.BytesIO(file_content.encode('utf-8')),
                    mimetype=mime_type,
                    resumable=True
                )
            else:
                # Assume it's bytes or file-like object
                media = MediaFileUpload(
                    file_content,
                    mimetype=mime_type,
                    resumable=True
                )
            
            # Upload file
            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()
            
            file_id = file['id']
            logger.info(f"Uploaded file to Google Drive: {file_name}")
            return file_id
            
        except Exception as e:
            logger.error(f"Error uploading file {file_name}: {e}")
            raise
    
    def upload_local_file(self, folder_id: str, local_file_path: Path) -> str:
        """Upload a local file to Google Drive"""
        
        try:
            file_metadata = {
                'name': local_file_path.name,
                'parents': [folder_id]
            }
            
            mime_type = mimetypes.guess_type(str(local_file_path))[0] or 'application/octet-stream'
            
            media = MediaFileUpload(
                str(local_file_path),
                mimetype=mime_type,
                resumable=True
            )
            
            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()
            
            file_id = file['id']
            logger.info(f"Uploaded local file to Google Drive: {local_file_path.name}")
            return file_id
            
        except Exception as e:
            logger.error(f"Error uploading local file {local_file_path}: {e}")
            raise
    
    def save_job_documents(self, company_name: str, role_category: str, job_id: str, 
                          documents: Dict[str, str]) -> Tuple[str, List[str]]:
        """
        Save job application documents to Google Drive
        Returns: (folder_id, list_of_file_ids)
        """
        
        # Create job folder
        folder_id = self.create_job_folder(company_name, role_category, job_id)
        
        file_ids = []
        
        try:
            for file_name, content in documents.items():
                if content:  # Only upload non-empty content
                    file_id = self.upload_file(folder_id, file_name, content)
                    file_ids.append(file_id)
            
            logger.info(f"Saved {len(file_ids)} documents for job {job_id} to Google Drive")
            return folder_id, file_ids
            
        except Exception as e:
            logger.error(f"Error saving job documents: {e}")
            raise
    
    def get_folder_link(self, folder_id: str) -> str:
        """Get shareable link for a folder"""
        return f"https://drive.google.com/drive/folders/{folder_id}"
    
    def get_file_link(self, file_id: str) -> str:
        """Get shareable link for a file"""
        return f"https://drive.google.com/file/d/{file_id}/view"
    
    def list_job_folders(self) -> List[Dict[str, Any]]:
        """List all job application folders"""
        
        folders = []
        
        try:
            query = f"parents in '{self.main_folder_id}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            results = self.service.files().list(
                q=query,
                fields='files(id, name, createdTime, modifiedTime)',
                orderBy='createdTime desc'
            ).execute()
            
            for folder in results.get('files', []):
                folder_info = {
                    'id': folder['id'],
                    'name': folder['name'],
                    'created_time': folder.get('createdTime'),
                    'modified_time': folder.get('modifiedTime'),
                    'link': self.get_folder_link(folder['id'])
                }
                
                # Try to get job details if available
                job_details = self._get_job_details_from_folder(folder['id'])
                if job_details:
                    folder_info.update(job_details)
                
                folders.append(folder_info)
            
        except Exception as e:
            logger.error(f"Error listing job folders: {e}")
        
        return folders
    
    def _get_job_details_from_folder(self, folder_id: str) -> Optional[Dict]:
        """Try to extract job details from job_details.json in folder"""
        
        try:
            # Look for job_details.json file
            query = f"parents in '{folder_id}' and name='{settings.JOB_DETAILS_FILENAME}' and trashed=false"
            results = self.service.files().list(q=query, fields='files(id)').execute()
            
            files = results.get('files', [])
            if not files:
                return None
            
            # Download and parse the file
            file_id = files[0]['id']
            request = self.service.files().get_media(fileId=file_id)
            
            file_content = io.BytesIO()
            downloader = MediaIoBaseDownload(file_content, request)
            
            done = False
            while done is False:
                status, done = downloader.next_chunk()
            
            # Parse JSON content
            content = file_content.getvalue().decode('utf-8')
            job_data = json.loads(content)
            
            return {
                'job_title': job_data.get('job_title'),
                'company_name': job_data.get('company_name'),
                'role_category': job_data.get('role_category'),
                'status': job_data.get('status')
            }
            
        except Exception as e:
            logger.debug(f"Could not extract job details from folder {folder_id}: {e}")
            return None
    
    def cleanup_old_folders(self, days_to_keep: int = 30) -> int:
        """Move old job folders to trash"""
        
        removed_count = 0
        cutoff_date = datetime.now().timestamp() - (days_to_keep * 24 * 60 * 60)
        
        try:
            folders = self.list_job_folders()
            
            for folder in folders:
                if folder.get('created_time'):
                    # Parse Google Drive timestamp
                    created_time = datetime.fromisoformat(
                        folder['created_time'].replace('Z', '+00:00')
                    ).timestamp()
                    
                    if created_time < cutoff_date:
                        # Move to trash
                        self.service.files().update(
                            fileId=folder['id'],
                            body={'trashed': True}
                        ).execute()
                        
                        removed_count += 1
                        logger.debug(f"Moved to trash: {folder['name']}")
            
            if removed_count > 0:
                logger.info(f"Moved {removed_count} old folders to trash")
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
        
        return removed_count
    
    def get_storage_stats(self) -> Dict[str, Any]:
        """Get Google Drive storage statistics"""
        
        stats = {
            'total_applications': 0,
            'total_files': 0,
            'storage_mode': 'cloud',
            'main_folder_link': self.get_folder_link(self.main_folder_id) if self.main_folder_id else None
        }
        
        try:
            # Count job folders
            folders = self.list_job_folders()
            stats['total_applications'] = len(folders)
            
            # Count total files (approximate)
            for folder in folders:
                folder_query = f"parents in '{folder['id']}' and trashed=false"
                folder_results = self.service.files().list(q=folder_query, fields='files(id)').execute()
                stats['total_files'] += len(folder_results.get('files', []))
            
        except Exception as e:
            logger.error(f"Error calculating storage stats: {e}")
        
        return stats
    
    def validate_drive_setup(self) -> List[str]:
        """Validate Google Drive setup and return any issues"""
        
        issues = []
        
        # Check credentials file
        if not self.credentials_file.exists():
            issues.append(f"Google Drive credentials file not found: {self.credentials_file}")
            return issues
        
        # Test service connection
        try:
            if not self.service:
                self._initialize_drive_service()
            
            # Test API access
            about = self.service.about().get(fields="user,storageQuota").execute()
            
            # Check storage quota if available
            storage_quota = about.get('storageQuota', {})
            if storage_quota:
                usage = int(storage_quota.get('usage', 0))
                limit = int(storage_quota.get('limit', 0))
                
                if limit > 0:
                    usage_percent = (usage / limit) * 100
                    if usage_percent > 90:
                        issues.append(f"Google Drive storage nearly full: {usage_percent:.1f}% used")
            
        except Exception as e:
            issues.append(f"Google Drive connection failed: {e}")
        
        # Test main folder access
        try:
            if not self.main_folder_id:
                self._ensure_main_folder()
        except Exception as e:
            issues.append(f"Cannot access/create main folder: {e}")
        
        return issues


# Factory function for easy access
def create_drive_manager() -> GoogleDriveManager:
    """Create a configured Google Drive manager instance"""
    return GoogleDriveManager()


# Global drive manager instance
_global_drive_manager: Optional[GoogleDriveManager] = None

def get_global_drive_manager() -> GoogleDriveManager:
    """Get or create the global drive manager instance"""
    global _global_drive_manager
    if _global_drive_manager is None:
        _global_drive_manager = create_drive_manager()
    return _global_drive_manager


# Validation helper
def validate_drive_dependencies() -> List[str]:
    """Validate that Google Drive dependencies are available"""
    issues = []
    
    if not GOOGLE_AVAILABLE:
        issues.append("Google API libraries not installed. Run: pip install google-api-python-client google-auth")
    
    return issues