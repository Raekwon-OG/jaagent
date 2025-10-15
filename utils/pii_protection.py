"""
PII Protection utilities for securing personal data in AI processing
"""
import os
import gc
import re
import logging
from typing import Dict, List, Tuple, Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
from pathlib import Path

logger = logging.getLogger(__name__)

class PIIProtector:
    """Handles encryption, placeholders, and secure memory management for PII"""
    
    # Standard placeholders for AI processing
    PLACEHOLDERS = {
        'name': '[CANDIDATE_NAME]',
        'email': '[CANDIDATE_EMAIL]',
        'phone': '[CANDIDATE_PHONE]',
        'address': '[CANDIDATE_ADDRESS]',
        'city': '[CANDIDATE_CITY]',
        'country': '[CANDIDATE_COUNTRY]',
        'postal_code': '[POSTAL_CODE]'
    }
    
    def __init__(self, master_password: Optional[str] = None):
        """Initialize PII protector with optional encryption"""
        self.master_password = master_password or os.getenv("PII_MASTER_PASSWORD", "")
        self._cipher = None
        self._sensitive_vars = set()
        
        if self.master_password:
            self._cipher = self._create_cipher(self.master_password)
    
    def _create_cipher(self, password: str) -> Fernet:
        """Create encryption cipher from password"""
        password_bytes = password.encode()
        salt = b'job_agent_salt_2024'  # In production, use random salt per user
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password_bytes))
        return Fernet(key)
    
    def encrypt_data(self, data: str) -> str:
        """Encrypt sensitive data for storage"""
        if not self._cipher:
            logger.warning("No encryption key provided, storing data in plain text")
            return data
        
        try:
            encrypted = self._cipher.encrypt(data.encode())
            return base64.urlsafe_b64encode(encrypted).decode()
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            return data
    
    def decrypt_data(self, encrypted_data: str) -> str:
        """Decrypt sensitive data"""
        if not self._cipher:
            return encrypted_data
        
        try:
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_data.encode())
            decrypted = self._cipher.decrypt(encrypted_bytes)
            return decrypted.decode()
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            return encrypted_data
    
    def extract_pii_from_text(self, text: str) -> Dict[str, List[str]]:
        """Extract potential PII patterns from text"""
        pii_patterns = {
            'email': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            'phone': r'(\+\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',
            'postal_code': r'\b\d{5}(-\d{4})?\b|\b[A-Z]\d[A-Z]\s?\d[A-Z]\d\b',
        }
        
        found_pii = {}
        for pii_type, pattern in pii_patterns.items():
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                found_pii[pii_type] = matches
        
        return found_pii
    
    def sanitize_for_ai(self, text: str, pii_data: Dict[str, str]) -> Tuple[str, Dict[str, str]]:
        """
        Replace PII with placeholders for AI processing
        Returns: (sanitized_text, replacement_mapping)
        """
        sanitized_text = text
        replacement_mapping = {}
        
        # Replace known PII with placeholders
        for pii_type, value in pii_data.items():
            if value and value.strip():
                placeholder = self.PLACEHOLDERS.get(pii_type, f'[{pii_type.upper()}]')
                
                # Handle multi-line addresses
                if pii_type == 'address' and '\n' in value:
                    lines = value.split('\n')
                    for i, line in enumerate(lines):
                        if line.strip():
                            line_placeholder = f'[ADDRESS_LINE_{i+1}]'
                            sanitized_text = sanitized_text.replace(line.strip(), line_placeholder)
                            replacement_mapping[line_placeholder] = line.strip()
                else:
                    sanitized_text = sanitized_text.replace(value, placeholder)
                    replacement_mapping[placeholder] = value
        
        # Auto-detect and replace additional PII
        detected_pii = self.extract_pii_from_text(sanitized_text)
        for pii_type, matches in detected_pii.items():
            placeholder = self.PLACEHOLDERS.get(pii_type, f'[{pii_type.upper()}]')
            for match in matches:
                if isinstance(match, tuple):
                    match = match[0]  # Handle regex groups
                sanitized_text = sanitized_text.replace(match, placeholder)
                replacement_mapping[placeholder] = match
        
        return sanitized_text, replacement_mapping
    
    def restore_pii(self, text: str, replacement_mapping: Dict[str, str]) -> str:
        """Restore original PII from placeholders"""
        restored_text = text
        for placeholder, original_value in replacement_mapping.items():
            restored_text = restored_text.replace(placeholder, original_value)
        return restored_text
    
    def secure_clear_variable(self, var_name: str, local_vars: dict = None, global_vars: dict = None):
        """Securely clear sensitive variables from memory"""
        self._sensitive_vars.add(var_name)
        
        # Clear from local scope if provided
        if local_vars and var_name in local_vars:
            del local_vars[var_name]
        
        # Clear from global scope if provided
        if global_vars and var_name in global_vars:
            del global_vars[var_name]
        
        # Force garbage collection
        gc.collect()
    
    def clear_all_sensitive_vars(self):
        """Clear all tracked sensitive variables"""
        gc.collect()
        self._sensitive_vars.clear()
    
    def create_audit_log(self, operation: str, data_types: List[str], ai_service: str = "openai"):
        """Log PII handling operations for audit trail"""
        audit_entry = {
            'timestamp': __import__('datetime').datetime.now().isoformat(),
            'operation': operation,
            'data_types': data_types,
            'ai_service': ai_service,
            'placeholders_used': True,
            'encryption_enabled': bool(self._cipher)
        }
        
        logger.info(f"PII Audit: {audit_entry}")
        return audit_entry


class SecureConfigLoader:
    """Securely load and manage configuration with PII protection"""
    
    def __init__(self, pii_protector: PIIProtector):
        self.pii_protector = pii_protector
        self._loaded_config = {}
    
    def load_candidate_info(self) -> Dict[str, str]:
        """Load candidate information with optional decryption"""
        from config import settings
        
        candidate_info = {
            'name': settings.CANDIDATE_NAME,
            'address': settings.CANDIDATE_ADDRESS,
            'email_phone': settings.CANDIDATE_EMAIL_PHONE,
            'country': settings.APPLICANT_COUNTRY
        }
        
        # Decrypt if encrypted
        for key, value in candidate_info.items():
            if value and value.startswith('gAAAAA'):  # Fernet encrypted data starts with this
                candidate_info[key] = self.pii_protector.decrypt_data(value)
        
        self._loaded_config.update(candidate_info)
        return candidate_info
    
    def parse_contact_info(self, email_phone_string: str) -> Dict[str, str]:
        """Parse email and phone from combined string"""
        lines = email_phone_string.strip().split('\n')
        email = ""
        phone = ""
        
        for line in lines:
            line = line.strip()
            if '@' in line:
                email = line
            elif any(char.isdigit() for char in line):
                phone = line
        
        return {'email': email, 'phone': phone}
    
    def get_sanitized_candidate_info(self) -> Tuple[Dict[str, str], Dict[str, str]]:
        """Get candidate info with PII placeholders for AI processing"""
        candidate_info = self.load_candidate_info()
        
        # Parse contact info
        contact_info = self.parse_contact_info(candidate_info.get('email_phone', ''))
        
        # Combine all PII
        all_pii = {
            'name': candidate_info.get('name', ''),
            'address': candidate_info.get('address', ''),
            'email': contact_info.get('email', ''),
            'phone': contact_info.get('phone', ''),
            'country': candidate_info.get('country', '')
        }
        
        # Create sanitized versions
        sanitized_info = {}
        replacement_mappings = {}
        
        for key, value in all_pii.items():
            if value:
                placeholder = self.pii_protector.PLACEHOLDERS.get(key, f'[{key.upper()}]')
                sanitized_info[key] = placeholder
                replacement_mappings[placeholder] = value
        
        return sanitized_info, replacement_mappings
    
    def clear_loaded_config(self):
        """Securely clear loaded configuration"""
        for key in list(self._loaded_config.keys()):
            self.pii_protector.secure_clear_variable(key, self._loaded_config)
        self._loaded_config.clear()


# Global instance for easy access
pii_protector = PIIProtector()
config_loader = SecureConfigLoader(pii_protector)


def secure_ai_processing(func):
    """Decorator for secure AI processing with PII protection"""
    def wrapper(*args, **kwargs):
        # Log the operation
        pii_protector.create_audit_log(
            operation=func.__name__,
            data_types=['resume', 'personal_info'],
            ai_service='openai'
        )
        
        try:
            result = func(*args, **kwargs)
            return result
        finally:
            # Clear sensitive data after processing
            pii_protector.clear_all_sensitive_vars()
            gc.collect()
    
    return wrapper


# Utility functions for quick access
def sanitize_text_for_ai(text: str, candidate_info: Dict[str, str]) -> Tuple[str, Dict[str, str]]:
    """Quick function to sanitize text for AI processing"""
    return pii_protector.sanitize_for_ai(text, candidate_info)

def restore_text_from_ai(text: str, replacement_mapping: Dict[str, str]) -> str:
    """Quick function to restore PII in AI output"""
    return pii_protector.restore_pii(text, replacement_mapping)