"""
Resume and cover letter tailoring service using AI with PII protection
"""
import logging
from typing import List, Optional, Dict, Any, Tuple, Union
from pathlib import Path

from config import settings
from services.gpt_service import get_global_gpt_service, safe_chat_completion
from utils.pii_protection import config_loader
from utils.ats_keywords import extract_ats_keywords

logger = logging.getLogger(__name__)

class TailoringService:
    """Handles AI-powered resume and cover letter tailoring with PII protection"""
    
    def __init__(self):
        self.gpt_service = get_global_gpt_service()
        self.align_prompt_file = Path(settings.ALIGN_PROMPT_FILE)
        
        # Load prompt template
        self._load_prompt_template()
    
    def _load_prompt_template(self):
        """Load the alignment prompt template"""
        try:
            if self.align_prompt_file.exists():
                with open(self.align_prompt_file, 'r', encoding='utf-8') as f:
                    self.align_prompt_template = f.read()
                logger.info(f"Loaded tailoring prompt from {self.align_prompt_file}")
            else:
                # Fallback to embedded prompt
                self.align_prompt_template = self._get_default_prompt()
                logger.warning(f"Prompt file not found, using default: {self.align_prompt_file}")
        except Exception as e:
            logger.error(f"Error loading prompt template: {e}")
            self.align_prompt_template = self._get_default_prompt()
    
    def _get_default_prompt(self) -> str:
        """Default prompt template if file is not found"""
        return """I'm applying for the job listed below.

Please help me with two things:

PART 1: Resume Optimization
Align my resume to this job while keeping everything honest and realistic.
Use keywords and phrasing that improve ATS compatibility.
Improve recruiter appeal by clearly showing how my experience fits.
Remove or reword points that are weak, redundant, or unrelated.
If adding any new bullet points, ensure they're realistic based on my background — even if slightly amplified, they should be things I could confidently pick up or already overlap with.
Update the professional summary to match the role but keep it grounded and credible.
Only edit the summary and experience sections.

PART 2: Cover Letter
Write a concise, professional, and natural-toned cover letter using a formal business letter format (include my address, company address, and date).
Keep the tone grounded and clear — avoid generic AI-style phrasing like "I am excited" or "passionate".
In the paragraph about the company, give a genuine, specific, and realistic reason for being interested in the role (e.g., what the company does, the scale of their work, the type of responsibilities, etc.).
Assume I'll be uploading this letter to an online application, but still keep it formal.

Here's the job description:
{{JOB_DESCRIPTION}}

Here's my current resume (summary + experience only) from the base {{ROLE_CATEGORY}} resume:
{{BASE_RESUME_TEXT}}

My contact info (for the letter header):
{{CANDIDATE_NAME}}
{{CANDIDATE_ADDRESS}}
{{CANDIDATE_EMAIL_PHONE}}

Company address (if provided):
{{COMPANY_NAME_AND_ADDRESS}}"""
    
    def tailor_application(self, job_description: str, base_resume_text: str, 
                          role_category: str, company_name: str, 
                          company_address: Optional[str] = None) -> Tuple[str, str, Dict]:
        """
        Tailor resume and generate cover letter for specific job
        Returns: (tailored_resume_text, tailored_cover_letter_text, metadata)
        """
        
        logger.info(f"Tailoring application for {role_category} role at {company_name}")
        
        try:
            # Get candidate information with PII protection
            sanitized_info, replacement_mappings = config_loader.get_sanitized_candidate_info()
            
            # Extract ATS keywords for context
            ats_keywords = extract_ats_keywords(job_description)
            
            # Prepare the prompt
            filled_prompt = self._fill_prompt_template(
                job_description=job_description,
                base_resume_text=base_resume_text,
                role_category=role_category,
                company_name=company_name,
                company_address=company_address,
                sanitized_info=sanitized_info
            )
            
            # Get AI response with PII protection
            system_prompt = "You are an expert resume writer and career coach. Help tailor the resume and create a cover letter as requested."
            
            ai_response, final_mappings = safe_chat_completion(
                system_prompt=system_prompt,
                user_content=filled_prompt,
                candidate_info=sanitized_info,
                temperature=0.7
            )
            
            # Parse the AI response into resume and cover letter
            resume_text, cover_letter_text = self._parse_ai_response(ai_response)
            
            # Create metadata
            tailoring_metadata = {
                'role_category': role_category,
                'company_name': company_name,
                'ats_keywords_found': len(ats_keywords),
                'base_resume_length': len(base_resume_text),
                'tailored_resume_length': len(resume_text),
                'cover_letter_length': len(cover_letter_text),
                'pii_protection_used': True,
                'placeholders_replaced': len(final_mappings)
            }
            
            logger.info(f"Successfully tailored application for {company_name}")
            
            return resume_text, cover_letter_text, tailoring_metadata
            
        except Exception as e:
            logger.error(f"Error tailoring application: {e}")
            raise
    
    def _fill_prompt_template(self, job_description: str, base_resume_text: str,
                            role_category: str, company_name: str,
                            company_address: Optional[str], 
                            sanitized_info: Dict[str, str]) -> str:
        """Fill the prompt template with actual values"""
        
        # Prepare company address
        company_name_and_address = company_name
        if company_address:
            company_name_and_address = f"{company_name}\n{company_address}"
        
        # Fill template placeholders
        filled_prompt = self.align_prompt_template.replace(
            "{{JOB_DESCRIPTION}}", job_description
        ).replace(
            "{{BASE_RESUME_TEXT}}", base_resume_text
        ).replace(
            "{{ROLE_CATEGORY}}", role_category
        ).replace(
            "{{CANDIDATE_NAME}}", sanitized_info.get('name', '[CANDIDATE_NAME]')
        ).replace(
            "{{CANDIDATE_ADDRESS}}", sanitized_info.get('address', '[CANDIDATE_ADDRESS]')
        ).replace(
            "{{CANDIDATE_EMAIL_PHONE}}", sanitized_info.get('email_phone', '[CANDIDATE_EMAIL_PHONE]')
        ).replace(
            "{{COMPANY_NAME_AND_ADDRESS}}", company_name_and_address
        )
        
        return filled_prompt
    
    def _parse_ai_response(self, ai_response: str) -> Tuple[str, str]:
        """Parse AI response to extract resume and cover letter sections"""
        
        # Look for section markers
        resume_markers = ["PART 1:", "Resume Optimization:", "RESUME:", "TAILORED RESUME:"]
        cover_letter_markers = ["PART 2:", "Cover Letter:", "COVER LETTER:"]
        
        lines = ai_response.split('\n')
        
        resume_section = []
        cover_letter_section = []
        current_section = None
        
        for line in lines:
            line_upper = line.strip().upper()
            
            # Check for section markers
            if any(marker.upper() in line_upper for marker in resume_markers):
                current_section = "resume"
                continue
            elif any(marker.upper() in line_upper for marker in cover_letter_markers):
                current_section = "cover_letter"
                continue
            
            # Add content to appropriate section
            if current_section == "resume":
                resume_section.append(line)
            elif current_section == "cover_letter":
                cover_letter_section.append(line)
            elif current_section is None:
                # Before any section markers, assume it's resume content
                resume_section.append(line)
        
        # Join sections
        resume_text = '\n'.join(resume_section).strip()
        cover_letter_text = '\n'.join(cover_letter_section).strip()
        
        # If parsing failed, try alternative approach
        if not resume_text or not cover_letter_text:
            resume_text, cover_letter_text = self._fallback_parse(ai_response)
        
        # Clean up the sections
        resume_text = self._clean_resume_text(resume_text)
        cover_letter_text = self._clean_cover_letter_text(cover_letter_text)
        
        return resume_text, cover_letter_text
    
    def _fallback_parse(self, ai_response: str) -> Tuple[str, str]:
        """Fallback parsing method if section markers aren't found"""
        
        # Split response roughly in half, assuming resume comes first
        lines = ai_response.split('\n')
        midpoint = len(lines) // 2
        
        # Look for a natural break point around the middle
        for i in range(midpoint - 10, midpoint + 10):
            if i < len(lines):
                line = lines[i].strip().lower()
                if ('dear' in line or 'sincerely' in line or 
                    'letter' in line or 'address' in line):
                    # Found likely start of cover letter
                    resume_text = '\n'.join(lines[:i]).strip()
                    cover_letter_text = '\n'.join(lines[i:]).strip()
                    return resume_text, cover_letter_text
        
        # If no natural break found, split at midpoint
        resume_text = '\n'.join(lines[:midpoint]).strip()
        cover_letter_text = '\n'.join(lines[midpoint:]).strip()
        
        return resume_text, cover_letter_text
    
    def _clean_resume_text(self, resume_text: str) -> str:
        """Clean and format resume text"""
        
        # Remove common AI artifacts
        artifacts_to_remove = [
            "Here's the tailored resume:",
            "Tailored Resume:",
            "Updated Resume:",
            "PART 1:",
            "Resume Optimization:"
        ]
        
        for artifact in artifacts_to_remove:
            resume_text = resume_text.replace(artifact, "")
        
        # Clean up extra whitespace
        lines = [line.strip() for line in resume_text.split('\n')]
        lines = [line for line in lines if line]  # Remove empty lines
        
        return '\n\n'.join(lines)
    
    def _clean_cover_letter_text(self, cover_letter_text: str) -> str:
        """Clean and format cover letter text"""
        
        # Remove common AI artifacts
        artifacts_to_remove = [
            "Here's the cover letter:",
            "Cover Letter:",
            "PART 2:",
            "Cover Letter:"
        ]
        
        for artifact in artifacts_to_remove:
            cover_letter_text = cover_letter_text.replace(artifact, "")
        
        # Ensure proper letter formatting
        lines = [line.strip() for line in cover_letter_text.split('\n')]
        
        # Add date if not present
        if not any('202' in line for line in lines[:5]):  # Check first 5 lines for year
            from datetime import datetime
            current_date = datetime.now().strftime("%B %d, %Y")
            lines.insert(0, current_date)
            lines.insert(1, "")  # Add spacing
        
        return '\n'.join(lines)
    
    def validate_tailoring_output(self, resume_text: str, cover_letter_text: str) -> Dict[str, bool]:
        """Validate that tailoring produced reasonable output"""
        
        validation_results = {
            'resume_has_content': len(resume_text.strip()) > 100,
            'cover_letter_has_content': len(cover_letter_text.strip()) > 100,
            'resume_has_summary': any(keyword in resume_text.lower() 
                                    for keyword in ['summary', 'profile', 'objective']),
            'resume_has_experience': any(keyword in resume_text.lower() 
                                       for keyword in ['experience', 'work', 'employment']),
            'cover_letter_has_greeting': any(keyword in cover_letter_text.lower() 
                                           for keyword in ['dear', 'hello', 'greetings']),
            'cover_letter_has_closing': any(keyword in cover_letter_text.lower() 
                                          for keyword in ['sincerely', 'regards', 'thank']),
            'no_placeholder_leakage': not any(placeholder in resume_text + cover_letter_text 
                                            for placeholder in ['[CANDIDATE_', '{{', '}}'])
        }
        
        # Overall validation
        validation_results['overall_valid'] = all(validation_results.values())
        
        return validation_results
    
    def get_tailoring_stats(self) -> Dict[str, any]:
        """Get statistics about tailoring operations"""
        
        return {
            'prompt_template_loaded': bool(self.align_prompt_template),
            'prompt_file_path': str(self.align_prompt_file),
            'prompt_file_exists': self.align_prompt_file.exists(),
            'gpt_model': self.gpt_service.chat_model,
            'pii_protection_enabled': True
        }


class QuickTailoringService:
    """Simplified tailoring service for quick operations"""
    
    def __init__(self):
        self.main_service = TailoringService()
    
    def quick_tailor(self, job_description: str, base_resume_text: str, 
                    company_name: str) -> Tuple[str, str]:
        """Quick tailoring without full metadata"""
        
        resume_text, cover_letter_text, _ = self.main_service.tailor_application(
            job_description=job_description,
            base_resume_text=base_resume_text,
            role_category="General",
            company_name=company_name
        )
        
        return resume_text, cover_letter_text


# Factory functions
def create_tailoring_service() -> TailoringService:
    """Create a configured tailoring service instance"""
    return TailoringService()

def create_quick_tailoring_service() -> QuickTailoringService:
    """Create a quick tailoring service instance"""
    return QuickTailoringService()


# Global service instance
_global_tailoring_service: Optional[TailoringService] = None

def get_global_tailoring_service() -> TailoringService:
    """Get or create the global tailoring service instance"""
    global _global_tailoring_service
    if _global_tailoring_service is None:
        _global_tailoring_service = create_tailoring_service()
    return _global_tailoring_service


# Convenience function
def tailor_resume_and_cover_letter(job_description: str, base_resume_text: str,
                                 role_category: str, company_name: str,
                                 company_address: Optional[str] = None) -> Tuple[str, str, Dict]:
    """Quick function to tailor resume and cover letter"""
    
    service = get_global_tailoring_service()
    return service.tailor_application(
        job_description, base_resume_text, role_category, 
        company_name, company_address
    )


# Validation helper
def validate_prompt_template() -> List[str]:
    """Validate that prompt template is properly configured"""
    
    issues = []
    
    prompt_file = Path(settings.ALIGN_PROMPT_FILE)
    
    if not prompt_file.exists():
        issues.append(f"Prompt template file not found: {prompt_file}")
        return issues
    
    try:
        with open(prompt_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check for required placeholders
        required_placeholders = [
            "{{JOB_DESCRIPTION}}",
            "{{BASE_RESUME_TEXT}}",
            "{{ROLE_CATEGORY}}",
            "{{CANDIDATE_NAME}}",
            "{{COMPANY_NAME_AND_ADDRESS}}"
        ]
        
        for placeholder in required_placeholders:
            if placeholder not in content:
                issues.append(f"Missing required placeholder: {placeholder}")
        
        # Check for reasonable content length
        if len(content) < 500:
            issues.append("Prompt template seems too short")
        
        # Check for key instructions
        key_instructions = ["resume", "cover letter", "honest", "realistic"]
        missing_instructions = [
            instruction for instruction in key_instructions 
            if instruction.lower() not in content.lower()
        ]
        
        if missing_instructions:
            issues.append(f"Prompt may be missing key instructions: {missing_instructions}")
    
    except Exception as e:
        issues.append(f"Error reading prompt template: {e}")
    
    return issues