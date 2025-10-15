"""
Job fit scoring service using AI to evaluate tailored resumes against job descriptions
"""
import json
import logging
import re
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path

from config import settings
from services.gpt_service import get_global_gpt_service, safe_chat_completion
from utils.pii_protection import pii_protector

logger = logging.getLogger(__name__)

class ScoringService:
    """Evaluates job fit after resume tailoring using AI"""
    
    def __init__(self):
        self.gpt_service = get_global_gpt_service()
        self.score_prompt_file = Path(settings.SCORE_PROMPT_FILE)
        self.fit_threshold = settings.FIT_SCORE_THRESHOLD
        
        # Load scoring prompt template
        self._load_scoring_prompt()
    
    def _load_scoring_prompt(self):
        """Load the scoring prompt template"""
        try:
            if self.score_prompt_file.exists():
                with open(self.score_prompt_file, 'r', encoding='utf-8') as f:
                    self.scoring_prompt_template = f.read()
                logger.info(f"Loaded scoring prompt from {self.score_prompt_file}")
            else:
                # Fallback to embedded prompt
                self.scoring_prompt_template = self._get_default_scoring_prompt()
                logger.warning(f"Scoring prompt file not found, using default: {self.score_prompt_file}")
        except Exception as e:
            logger.error(f"Error loading scoring prompt: {e}")
            self.scoring_prompt_template = self._get_default_scoring_prompt()
    
    def _get_default_scoring_prompt(self) -> str:
        """Default scoring prompt if file is not found"""
        return """Evaluate the candidate's TAILORED RESUME against this JOB DESCRIPTION.

Return a single JSON object with:
- "score": number between 0 and 10 (one decimal), where 8.5+ indicates strong alignment
- "gaps": array of the top 3–5 missing or weak requirements
- "notes": one short sentence explaining the score

JOB DESCRIPTION:
{{JOB_DESCRIPTION}}

TAILORED RESUME (summary + experience only):
{{TAILORED_RESUME_TEXT}}"""
    
    def score_job_fit(self, job_description: str, tailored_resume_text: str,
                     job_title: str = "", company_name: str = "") -> Dict[str, Any]:
        """
        Score how well the tailored resume fits the job description
        Returns: scoring results with score, gaps, and analysis
        """
        
        logger.info(f"Scoring job fit for {job_title} at {company_name}")
        
        try:
            # Sanitize inputs for AI processing (minimal PII in job descriptions/resumes)
            candidate_info = {}  # Empty since we're not sending personal details
            
            # Fill the scoring prompt
            filled_prompt = self._fill_scoring_prompt(job_description, tailored_resume_text)
            
            # Get AI response with PII protection
            system_prompt = ("You are an expert recruiter and hiring manager. "
                           "Evaluate resume-job fit objectively and return valid JSON only.")
            
            ai_response, _ = safe_chat_completion(
                system_prompt=system_prompt,
                user_content=filled_prompt,
                candidate_info=candidate_info,
                temperature=0.3  # Lower temperature for more consistent scoring
            )
            
            # Parse the AI response
            scoring_result = self._parse_scoring_response(ai_response)
            
            # Add metadata
            scoring_result.update({
                'job_title': job_title,
                'company_name': company_name,
                'fit_threshold': self.fit_threshold,
                'meets_threshold': scoring_result.get('score', 0) >= self.fit_threshold,
                'resume_length': len(tailored_resume_text),
                'job_description_length': len(job_description)
            })
            
            # Validate score
            self._validate_scoring_result(scoring_result)
            
            logger.info(f"Job fit score: {scoring_result.get('score', 0):.1f}/10 "
                       f"(threshold: {self.fit_threshold})")
            
            return scoring_result
            
        except Exception as e:
            logger.error(f"Error scoring job fit: {e}")
            # Return a safe fallback score
            return self._get_fallback_score(str(e))
    
    def _fill_scoring_prompt(self, job_description: str, tailored_resume_text: str) -> str:
        """Fill the scoring prompt template with actual values"""
        
        filled_prompt = self.scoring_prompt_template.replace(
            "{{JOB_DESCRIPTION}}", job_description
        ).replace(
            "{{TAILORED_RESUME_TEXT}}", tailored_resume_text
        )
        
        return filled_prompt
    
    def _parse_scoring_response(self, ai_response: str) -> Dict[str, Any]:
        """Parse AI response to extract scoring information"""
        
        # Try to extract JSON from the response
        json_match = re.search(r'\{.*\}', ai_response, re.DOTALL)
        
        if json_match:
            json_str = json_match.group()
            try:
                result = json.loads(json_str)
                
                # Ensure required fields exist
                if 'score' not in result:
                    result['score'] = 0.0
                if 'gaps' not in result:
                    result['gaps'] = []
                if 'notes' not in result:
                    result['notes'] = "No analysis provided"
                
                # Validate and clean score
                score = float(result['score'])
                result['score'] = max(0.0, min(10.0, score))  # Clamp between 0-10
                
                return result
                
            except json.JSONDecodeError as e:
                logger.error(f"JSON parsing failed: {e}")
                logger.error(f"AI response: {ai_response}")
                return self._extract_score_manually(ai_response)
        else:
            logger.warning("No JSON found in AI response, attempting manual extraction")
            return self._extract_score_manually(ai_response)
    
    def _extract_score_manually(self, ai_response: str) -> Dict[str, Any]:
        """Manually extract score information from non-JSON response"""
        
        # Look for score patterns
        score_patterns = [
            r'score[:\s]*(\d+\.?\d*)',
            r'(\d+\.?\d*)[/\s]*10',
            r'(\d+\.?\d*)\s*out\s*of\s*10'
        ]
        
        score = 0.0
        for pattern in score_patterns:
            match = re.search(pattern, ai_response, re.IGNORECASE)
            if match:
                try:
                    score = float(match.group(1))
                    break
                except (ValueError, IndexError):
                    continue
        
        # Extract gaps (look for bullet points or numbered lists)
        gaps = []
        lines = ai_response.split('\n')
        for line in lines:
            line = line.strip()
            if (line.startswith(('-', '*', '•')) or 
                re.match(r'^\d+\.', line) or
                'gap' in line.lower() or 'missing' in line.lower()):
                # Clean up the gap description
                gap = re.sub(r'^[-*•\d.\s]+', '', line).strip()
                if gap and len(gap) > 10:  # Reasonable gap description
                    gaps.append(gap)
        
        # Extract notes (usually the last paragraph or summary)
        notes = "Score extracted manually from response"
        if len(ai_response) > 50:
            # Try to get a meaningful summary
            sentences = ai_response.split('.')
            for sentence in reversed(sentences):
                if len(sentence.strip()) > 20 and 'score' in sentence.lower():
                    notes = sentence.strip()
                    break
        
        return {
            'score': max(0.0, min(10.0, score)),
            'gaps': gaps[:5],  # Limit to top 5
            'notes': notes,
            'parsing_method': 'manual'
        }
    
    def _validate_scoring_result(self, result: Dict[str, Any]):
        """Validate scoring result and fix common issues"""
        
        # Ensure score is in valid range
        if 'score' in result:
            score = result['score']
            if not isinstance(score, (int, float)):
                result['score'] = 0.0
            else:
                result['score'] = max(0.0, min(10.0, float(score)))
        
        # Ensure gaps is a list
        if 'gaps' not in result or not isinstance(result['gaps'], list):
            result['gaps'] = []
        
        # Limit gaps to reasonable number
        if len(result['gaps']) > 5:
            result['gaps'] = result['gaps'][:5]
        
        # Ensure notes is a string
        if 'notes' not in result or not isinstance(result['notes'], str):
            result['notes'] = "No analysis notes available"
        
        # Truncate overly long notes
        if len(result['notes']) > 500:
            result['notes'] = result['notes'][:500] + "..."
    
    def _get_fallback_score(self, error_message: str) -> Dict[str, Any]:
        """Return a safe fallback score when AI scoring fails"""
        
        return {
            'score': 0.0,
            'gaps': ["Unable to analyze job fit due to technical error"],
            'notes': f"Scoring failed: {error_message[:100]}",
            'meets_threshold': False,
            'error': True,
            'fallback_used': True
        }
    
    def batch_score_jobs(self, job_resume_pairs: List[Tuple[str, str, str]]) -> List[Dict[str, Any]]:
        """
        Score multiple job-resume pairs efficiently
        job_resume_pairs: List of (job_description, tailored_resume, job_title) tuples
        """
        
        results = []
        
        for i, (job_desc, resume_text, job_title) in enumerate(job_resume_pairs):
            logger.info(f"Scoring job {i+1}/{len(job_resume_pairs)}: {job_title}")
            
            try:
                result = self.score_job_fit(job_desc, resume_text, job_title)
                result['batch_index'] = i
                results.append(result)
                
            except Exception as e:
                logger.error(f"Error scoring job {i+1}: {e}")
                fallback = self._get_fallback_score(str(e))
                fallback['batch_index'] = i
                fallback['job_title'] = job_title
                results.append(fallback)
        
        return results
    
    def analyze_scoring_patterns(self, scoring_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze patterns in scoring results for insights"""
        
        if not scoring_results:
            return {'error': 'No scoring results to analyze'}
        
        scores = [r.get('score', 0) for r in scoring_results]
        
        analysis = {
            'total_jobs_scored': len(scoring_results),
            'average_score': sum(scores) / len(scores) if scores else 0,
            'highest_score': max(scores) if scores else 0,
            'lowest_score': min(scores) if scores else 0,
            'scores_above_threshold': sum(1 for s in scores if s >= self.fit_threshold),
            'success_rate': (sum(1 for s in scores if s >= self.fit_threshold) / len(scores)) * 100,
            'score_distribution': {
                'excellent (9.0+)': sum(1 for s in scores if s >= 9.0),
                'good (8.0-8.9)': sum(1 for s in scores if 8.0 <= s < 9.0),
                'fair (6.0-7.9)': sum(1 for s in scores if 6.0 <= s < 8.0),
                'poor (< 6.0)': sum(1 for s in scores if s < 6.0)
            }
        }
        
        # Common gaps analysis
        all_gaps = []
        for result in scoring_results:
            if 'gaps' in result and isinstance(result['gaps'], list):
                all_gaps.extend(result['gaps'])
        
        # Count gap frequency
        gap_frequency = {}
        for gap in all_gaps:
            gap_lower = gap.lower()
            # Group similar gaps
            for existing_gap in gap_frequency:
                if (len(set(gap_lower.split()) & set(existing_gap.split())) >= 2 and
                    len(gap_lower.split()) >= 2):
                    gap_frequency[existing_gap] += 1
                    break
            else:
                gap_frequency[gap] = 1
        
        # Get top gaps
        analysis['common_gaps'] = sorted(gap_frequency.items(), key=lambda x: x[1], reverse=True)[:10]
        
        return analysis
    
    def get_scoring_recommendations(self, scoring_result: Dict[str, Any]) -> List[str]:
        """Generate recommendations based on scoring result"""
        
        recommendations = []
        score = scoring_result.get('score', 0)
        gaps = scoring_result.get('gaps', [])
        
    def get_scoring_recommendations(self, scoring_result: Dict[str, Any]) -> List[str]:
        """Generate recommendations based on scoring result"""
        
        recommendations = []
        score = scoring_result.get('score', 0)
        gaps = scoring_result.get('gaps', [])
        
        if score >= 9.0:
            recommendations.append("Excellent match! This application should be prioritized.")
        elif score >= 8.5:
            recommendations.append("Strong match. Proceed with application.")
        elif score >= 7.0:
            recommendations.append("Good potential match, but consider addressing key gaps.")
        elif score >= 5.0:
            recommendations.append("Moderate fit. Significant improvements needed.")
        else:
            recommendations.append("Poor fit. Consider focusing on better-matched opportunities.")
        
        # Gap-specific recommendations
        if gaps:
            recommendations.append(f"Address top gaps: {', '.join(gaps[:3])}")
        
        # Specific improvement suggestions based on common patterns
        gap_text = ' '.join(gaps).lower()
        
        if any(keyword in gap_text for keyword in ['experience', 'years']):
            recommendations.append("Consider highlighting relevant experience more prominently.")
        
        if any(keyword in gap_text for keyword in ['skill', 'technology', 'programming']):
            recommendations.append("Emphasize technical skills that match job requirements.")
        
        if any(keyword in gap_text for keyword in ['education', 'degree', 'certification']):
            recommendations.append("Highlight relevant education, certifications, or training.")
        
        if any(keyword in gap_text for keyword in ['leadership', 'management']):
            recommendations.append("Showcase leadership experience and management capabilities.")
        
        return recommendations


# Factory function
def create_scoring_service() -> ScoringService:
    """Create a configured scoring service instance"""
    return ScoringService()


# Global service instance
_global_scoring_service: Optional[ScoringService] = None

def get_global_scoring_service() -> ScoringService:
    """Get or create the global scoring service instance"""
    global _global_scoring_service
    if _global_scoring_service is None:
        _global_scoring_service = create_scoring_service()
    return _global_scoring_service


# Convenience functions
def score_job_fit(job_description: str, tailored_resume_text: str,
                 job_title: str = "", company_name: str = "") -> Dict[str, Any]:
    """Quick function to score job fit"""
    service = get_global_scoring_service()
    return service.score_job_fit(job_description, tailored_resume_text, job_title, company_name)

def meets_fit_threshold(scoring_result: Dict[str, Any]) -> bool:
    """Check if scoring result meets the configured threshold"""
    return scoring_result.get('score', 0) >= settings.FIT_SCORE_THRESHOLD

def get_fit_recommendation(scoring_result: Dict[str, Any]) -> str:
    """Get simple recommendation based on score"""
    score = scoring_result.get('score', 0)
    
    if score >= settings.FIT_SCORE_THRESHOLD:
        return "PROCEED"
    else:
        return "IGNORE"


# Validation helper
def validate_scoring_setup() -> List[str]:
    """Validate scoring service setup"""
    
    issues = []
    
    # Check prompt file
    prompt_file = Path(settings.SCORE_PROMPT_FILE)
    if not prompt_file.exists():
        issues.append(f"Scoring prompt file not found: {prompt_file}")
    else:
        try:
            with open(prompt_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            required_placeholders = ["{{JOB_DESCRIPTION}}", "{{TAILORED_RESUME_TEXT}}"]
            for placeholder in required_placeholders:
                if placeholder not in content:
                    issues.append(f"Missing required placeholder in scoring prompt: {placeholder}")
            
        except Exception as e:
            issues.append(f"Error reading scoring prompt: {e}")
    
    # Check threshold value
    if not (0 <= settings.FIT_SCORE_THRESHOLD <= 10):
        issues.append(f"Invalid fit score threshold: {settings.FIT_SCORE_THRESHOLD}")
    
    # Test scoring service
    try:
        service = create_scoring_service()
        test_result = service.score_job_fit(
            "Test job description requiring Python programming",
            "Professional Summary: Experienced Python developer with 5 years experience."
        )
        
        if 'score' not in test_result:
            issues.append("Scoring service test failed - no score returned")
        
    except Exception as e:
        issues.append(f"Scoring service test failed: {e}")
    
    return issues