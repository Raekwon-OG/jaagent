"""
ATS keyword extraction utilities for job descriptions
"""
import re
import logging
from typing import Dict, List, Set, Tuple, Optional
from collections import Counter

logger = logging.getLogger(__name__)

class ATSKeywordExtractor:
    """Extracts ATS-friendly keywords from job descriptions"""
    
    def __init__(self):
        # Common technical skills patterns
        self.tech_skills_patterns = {
            'programming_languages': [
                'python', 'java', 'javascript', 'typescript', 'c++', 'c#', 'php', 'ruby', 'go', 'rust',
                'scala', 'kotlin', 'swift', 'objective-c', 'perl', 'r', 'matlab', 'sql', 'html', 'css'
            ],
            'frameworks_libraries': [
                'react', 'angular', 'vue', 'node.js', 'express', 'django', 'flask', 'spring', 'laravel',
                'rails', 'bootstrap', 'jquery', 'tensorflow', 'pytorch', 'pandas', 'numpy', 'scikit-learn'
            ],
            'databases': [
                'mysql', 'postgresql', 'mongodb', 'redis', 'elasticsearch', 'oracle', 'sqlite', 'cassandra',
                'dynamodb', 'firebase', 'mariadb'
            ],
            'cloud_platforms': [
                'aws', 'azure', 'gcp', 'google cloud', 'docker', 'kubernetes', 'jenkins', 'terraform',
                'ansible', 'vagrant'
            ],
            'tools_technologies': [
                'git', 'github', 'gitlab', 'jira', 'confluence', 'slack', 'teams', 'linux', 'windows',
                'macos', 'bash', 'powershell', 'vim', 'vscode', 'intellij'
            ]
        }
        
        # Soft skills and qualifications
        self.soft_skills = [
            'leadership', 'communication', 'teamwork', 'problem solving', 'analytical',
            'project management', 'agile', 'scrum', 'collaboration', 'mentoring',
            'critical thinking', 'adaptability', 'creativity', 'time management'
        ]
        
        # Experience level indicators
        self.experience_levels = [
            'entry level', 'junior', 'senior', 'lead', 'principal', 'staff', 'architect',
            'manager', 'director', 'years experience', 'years of experience'
        ]
        
        # Common stop words to filter out
        self.stop_words = {
            'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by',
            'from', 'up', 'about', 'into', 'through', 'during', 'before', 'after', 'above',
            'below', 'between', 'among', 'this', 'that', 'these', 'those', 'is', 'was',
            'are', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did',
            'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can', 'shall'
        }
    
    def extract_keywords(self, job_description: str) -> Dict[str, List[str]]:
        """Extract categorized keywords from job description"""
        
        logger.debug(f"Extracting keywords from job description ({len(job_description)} chars)")
        
        # Normalize text
        normalized_text = self._normalize_text(job_description)
        
        # Extract different types of keywords
        keywords = {
            'technical_skills': self._extract_technical_skills(normalized_text),
            'soft_skills': self._extract_soft_skills(normalized_text),
            'experience_requirements': self._extract_experience_requirements(normalized_text),
            'certifications': self._extract_certifications(normalized_text),
            'industry_terms': self._extract_industry_terms(normalized_text),
            'action_verbs': self._extract_action_verbs(normalized_text),
            'key_phrases': self._extract_key_phrases(normalized_text)
        }
        
        # Remove duplicates and empty entries
        for category in keywords:
            keywords[category] = list(set(filter(None, keywords[category])))
        
        logger.info(f"Extracted {sum(len(v) for v in keywords.values())} total keywords")
        
        return keywords
    
    def _normalize_text(self, text: str) -> str:
        """Normalize text for better keyword extraction"""
        
        # Convert to lowercase
        text = text.lower()
        
        # Remove extra whitespace and newlines
        text = re.sub(r'\s+', ' ', text)
        
        # Remove special characters but keep periods, commas, and hyphens
        text = re.sub(r'[^\w\s\.\,\-]', ' ', text)
        
        return text.strip()
    
    def _extract_technical_skills(self, text: str) -> List[str]:
        """Extract technical skills and technologies"""
        
        found_skills = []
        
        # Search for predefined technical skills
        for category, skills in self.tech_skills_patterns.items():
            for skill in skills:
                # Create pattern that matches skill as whole word
                pattern = rf'\b{re.escape(skill)}\b'
                if re.search(pattern, text, re.IGNORECASE):
                    found_skills.append(skill)
        
        # Extract version numbers with technologies
        version_patterns = [
            r'(\w+)\s+(\d+(?:\.\d+)*)',  # Python 3.8, Java 11
            r'(\w+)\s+v(\d+(?:\.\d+)*)', # Node.js v16
        ]
        
        for pattern in version_patterns:
            matches = re.findall(pattern, text)
            for tech, version in matches:
                if len(tech) > 2:  # Avoid short meaningless matches
                    found_skills.append(f"{tech} {version}")
        
        return found_skills
    
    def _extract_soft_skills(self, text: str) -> List[str]:
        """Extract soft skills and competencies"""
        
        found_skills = []
        
        for skill in self.soft_skills:
            pattern = rf'\b{re.escape(skill)}\b'
            if re.search(pattern, text, re.IGNORECASE):
                found_skills.append(skill)
        
        # Extract additional soft skills using common patterns
        soft_skill_patterns = [
            r'excellent\s+(\w+(?:\s+\w+)?)\s+skills',
            r'strong\s+(\w+(?:\s+\w+)?)\s+skills',
            r'proven\s+(\w+(?:\s+\w+)?)\s+skills',
            r'(\w+(?:\s+\w+)?)\s+skills\s+required',
        ]
        
        for pattern in soft_skill_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                if isinstance(match, tuple):
                    match = ' '.join(match)
                if match and match not in self.stop_words:
                    found_skills.append(match.strip())
        
        return found_skills
    
    def _extract_experience_requirements(self, text: str) -> List[str]:
        """Extract experience level and duration requirements"""
        
        experience_terms = []
        
        # Extract years of experience
        year_patterns = [
            r'(\d+)\+?\s*years?\s+(?:of\s+)?experience',
            r'(\d+)-(\d+)\s*years?\s+(?:of\s+)?experience',
            r'minimum\s+(\d+)\s*years?',
            r'at\s+least\s+(\d+)\s*years?'
        ]
        
        for pattern in year_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                if isinstance(match, tuple):
                    if len(match) == 2:  # Range like "3-5 years"
                        experience_terms.append(f"{match[0]}-{match[1]} years experience")
                    else:
                        experience_terms.append(f"{match[0]} years experience")
                else:
                    experience_terms.append(f"{match} years experience")
        
        # Extract experience levels
        for level in self.experience_levels:
            pattern = rf'\b{re.escape(level)}\b'
            if re.search(pattern, text, re.IGNORECASE):
                experience_terms.append(level)
        
        return experience_terms
    
    def _extract_certifications(self, text: str) -> List[str]:
        """Extract certification requirements"""
        
        certifications = []
        
        # Common certification patterns
        cert_patterns = [
            r'\b([A-Z]{2,})\s+certified\b',
            r'\bcertification\s+in\s+([A-Za-z\s]+)',
            r'\b([A-Za-z\s]+)\s+certification\b',
            r'\b(AWS|Azure|GCP|Google Cloud)\s+([A-Za-z\s]+)',
            r'\b(Cisco|Microsoft|Oracle|Salesforce|Amazon)\s+([A-Za-z\s]+)',
        ]
        
        for pattern in cert_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    cert = ' '.join(filter(None, match)).strip()
                else:
                    cert = match.strip()
                
                if cert and len(cert) > 2:
                    certifications.append(cert)
        
        # Degree requirements
        degree_patterns = [
            r"bachelor'?s?\s+(?:degree\s+)?(?:in\s+)?([A-Za-z\s]+)",
            r"master'?s?\s+(?:degree\s+)?(?:in\s+)?([A-Za-z\s]+)",
            r"phd\s+(?:in\s+)?([A-Za-z\s]+)",
            r"([A-Za-z\s]+)\s+degree"
        ]
        
        for pattern in degree_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                degree = match.strip()
                if degree and len(degree) > 2 and degree not in self.stop_words:
                    certifications.append(f"Degree in {degree}")
        
        return certifications
    
    def _extract_industry_terms(self, text: str) -> List[str]:
        """Extract industry-specific terms and methodologies"""
        
        industry_terms = []
        
        # Common methodologies and frameworks
        methodologies = [
            'agile', 'scrum', 'kanban', 'waterfall', 'devops', 'ci/cd', 'tdd', 'bdd',
            'microservices', 'api', 'rest', 'graphql', 'soap', 'json', 'xml',
            'machine learning', 'artificial intelligence', 'data science', 'big data',
            'blockchain', 'cybersecurity', 'cloud computing', 'iot'
        ]
        
        for term in methodologies:
            pattern = rf'\b{re.escape(term)}\b'
            if re.search(pattern, text, re.IGNORECASE):
                industry_terms.append(term)
        
        # Extract acronyms (likely to be industry terms)
        acronym_pattern = r'\b[A-Z]{2,}\b'
        acronyms = re.findall(acronym_pattern, text)
        
        # Filter out common non-technical acronyms
        non_technical = {'AND', 'THE', 'FOR', 'WITH', 'FROM', 'THIS', 'THAT', 'ARE', 'YOU', 'ALL'}
        technical_acronyms = [acr for acr in acronyms if acr not in non_technical and len(acr) <= 6]
        
        industry_terms.extend(technical_acronyms)
        
        return industry_terms
    
    def _extract_action_verbs(self, text: str) -> List[str]:
        """Extract action verbs that are good for resume optimization"""
        
        action_verbs = [
            'develop', 'build', 'create', 'design', 'implement', 'manage', 'lead',
            'coordinate', 'collaborate', 'optimize', 'improve', 'enhance', 'streamline',
            'troubleshoot', 'debug', 'analyze', 'evaluate', 'architect', 'deploy',
            'maintain', 'support', 'configure', 'integrate', 'automate', 'test',
            'monitor', 'document', 'train', 'mentor', 'guide', 'facilitate'
        ]
        
        found_verbs = []
        
        for verb in action_verbs:
            # Look for verb in various forms
            patterns = [
                rf'\b{verb}\b',
                rf'\b{verb}s\b',
                rf'\b{verb}ed\b',
                rf'\b{verb}ing\b'
            ]
            
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    found_verbs.append(verb)
                    break
        
        return found_verbs
    
    def _extract_key_phrases(self, text: str) -> List[str]:
        """Extract important multi-word phrases"""
        
        # Common important phrases in job descriptions
        key_phrase_patterns = [
            r'cross[- ]functional\s+teams?',
            r'full[- ]stack\s+development',
            r'end[- ]to[- ]end\s+\w+',
            r'real[- ]time\s+\w+',
            r'large[- ]scale\s+\w+',
            r'high[- ]performance\s+\w+',
            r'user[- ]friendly\s+\w+',
            r'best\s+practices',
            r'code\s+review',
            r'technical\s+documentation',
            r'system\s+architecture',
            r'database\s+design',
            r'performance\s+optimization',
            r'security\s+best\s+practices'
        ]
        
        found_phrases = []
        
        for pattern in key_phrase_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            found_phrases.extend(matches)
        
        return found_phrases
    
    def get_keyword_frequency(self, job_description: str) -> Dict[str, int]:
        """Get frequency count of all keywords"""
        
        keywords = self.extract_keywords(job_description)
        
        # Flatten all keywords
        all_keywords = []
        for category, keyword_list in keywords.items():
            all_keywords.extend(keyword_list)
        
        # Count frequencies
        frequency = Counter(all_keywords)
        
        return dict(frequency)
    
    def get_top_keywords(self, job_description: str, limit: int = 20) -> List[Tuple[str, int]]:
        """Get top keywords by frequency"""
        
        frequency = self.get_keyword_frequency(job_description)
        return frequency.most_common(limit)
    
    def compare_keywords(self, job_description: str, resume_text: str) -> Dict[str, any]:
        """Compare keywords between job description and resume"""
        
        job_keywords = self.extract_keywords(job_description)
        resume_keywords = self.extract_keywords(resume_text)
        
        # Flatten keyword lists
        job_set = set()
        resume_set = set()
        
        for category in job_keywords:
            job_set.update([kw.lower() for kw in job_keywords[category]])
        
        for category in resume_keywords:
            resume_set.update([kw.lower() for kw in resume_keywords[category]])
        
        # Calculate overlap
        overlap = job_set.intersection(resume_set)
        missing = job_set - resume_set
        extra = resume_set - job_set
        
        return {
            'job_keywords_count': len(job_set),
            'resume_keywords_count': len(resume_set),
            'overlap_count': len(overlap),
            'overlap_percentage': (len(overlap) / len(job_set)) * 100 if job_set else 0,
            'matching_keywords': list(overlap),
            'missing_keywords': list(missing),
            'extra_keywords': list(extra)
        }


# Factory function
def create_ats_extractor() -> ATSKeywordExtractor:
    """Create ATS keyword extractor instance"""
    return ATSKeywordExtractor()


# Global extractor instance
_global_extractor: Optional[ATSKeywordExtractor] = None

def get_global_extractor() -> ATSKeywordExtractor:
    """Get or create global ATS keyword extractor"""
    global _global_extractor
    if _global_extractor is None:
        _global_extractor = create_ats_extractor()
    return _global_extractor


# Convenience functions
def extract_ats_keywords(job_description: str) -> Dict[str, List[str]]:
    """Quick function to extract ATS keywords"""
    extractor = get_global_extractor()
    return extractor.extract_keywords(job_description)

def get_keyword_match_score(job_description: str, resume_text: str) -> float:
    """Get keyword matching score between job and resume"""
    extractor = get_global_extractor()
    comparison = extractor.compare_keywords(job_description, resume_text)
    return comparison['overlap_percentage']

def get_missing_keywords(job_description: str, resume_text: str) -> List[str]:
    """Get keywords present in job but missing from resume"""
    extractor = get_global_extractor()
    comparison = extractor.compare_keywords(job_description, resume_text)
    return comparison['missing_keywords']