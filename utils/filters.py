"""
Enhanced location and work permit filtering for international job seekers
"""
import re
import logging
from typing import Dict, List, Tuple, Optional, NamedTuple
from dataclasses import dataclass
from config import settings

logger = logging.getLogger(__name__)

@dataclass
class FilterDecision:
    """Result of filtering decision"""
    should_stop: bool
    reason: str
    details: Dict[str, any]

class LocationInfo(NamedTuple):
    """Structured location information"""
    country: str
    city: str
    region: str  # state/province
    is_remote: bool

class WorkPermitAnalyzer:
    """Analyzes work permit and visa sponsorship requirements"""
    
    def __init__(self):
        self.restrictive_terms = [term.lower() for term in settings.RESTRICTIVE_LOCAL_TERMS]
        self.positive_terms = [term.lower() for term in settings.POSITIVE_SPONSORSHIP_TERMS]
        self.sponsorship_friendly_countries = [country.lower() for country in settings.SPONSORSHIP_FRIENDLY_COUNTRIES]
        self.applicant_country = settings.APPLICANT_COUNTRY.lower()
    
    def extract_location_info(self, location_string: str, job_description: str = "") -> LocationInfo:
        """Extract structured location information from job posting"""
        location_lower = location_string.lower()
        
        # Check for remote work indicators
        remote_indicators = [
            'remote', 'work from home', 'wfh', 'telecommute', 'distributed',
            'anywhere', 'worldwide', 'global', 'virtual'
        ]
        is_remote = any(indicator in location_lower for indicator in remote_indicators)
        
        # Also check job description for remote indicators
        if job_description:
            jd_lower = job_description.lower()
            is_remote = is_remote or any(indicator in jd_lower for indicator in remote_indicators)
        
        # Extract country information
        country = self._extract_country(location_string)
        city = self._extract_city(location_string)
        region = self._extract_region(location_string)
        
        return LocationInfo(
            country=country,
            city=city,
            region=region,
            is_remote=is_remote
        )
    
    def _extract_country(self, location_string: str) -> str:
        """Extract country from location string"""
        location_lower = location_string.lower()
        
        # Common country patterns
        country_patterns = {
            'united states': ['united states', 'usa', 'us', 'america'],
            'united kingdom': ['united kingdom', 'uk', 'britain', 'england', 'scotland', 'wales'],
            'canada': ['canada', 'canadian'],
            'australia': ['australia', 'australian'],
            'germany': ['germany', 'german', 'deutschland'],
            'netherlands': ['netherlands', 'holland', 'dutch'],
            'france': ['france', 'french'],
            'singapore': ['singapore'],
            'ireland': ['ireland', 'irish'],
            'new zealand': ['new zealand'],
            'switzerland': ['switzerland', 'swiss'],
            'sweden': ['sweden', 'swedish'],
            'norway': ['norway', 'norwegian'],
            'denmark': ['denmark', 'danish']
        }
        
        for country, patterns in country_patterns.items():
            if any(pattern in location_lower for pattern in patterns):
                return country.title()
        
        # If no specific country found, try to extract from end of location string
        parts = location_string.split(',')
        if len(parts) >= 2:
            potential_country = parts[-1].strip()
            return potential_country.title()
        
        return "Unknown"
    
    def _extract_city(self, location_string: str) -> str:
        """Extract city from location string"""
        parts = [part.strip() for part in location_string.split(',')]
        if parts:
            return parts[0].title()
        return "Unknown"
    
    def _extract_region(self, location_string: str) -> str:
        """Extract state/province from location string"""
        parts = [part.strip() for part in location_string.split(',')]
        if len(parts) >= 2:
            return parts[1].title()
        return ""
    
    def find_restrictive_indicators(self, job_description: str) -> List[str]:
        """Find work permit restriction indicators in job description"""
        jd_lower = job_description.lower()
        found_restrictions = []
        
        for term in self.restrictive_terms:
            if term in jd_lower:
                found_restrictions.append(term)
        
        return found_restrictions
    
    def find_positive_indicators(self, job_description: str) -> List[str]:
        """Find visa sponsorship indicators in job description"""
        jd_lower = job_description.lower()
        found_positive = []
        
        for term in self.positive_terms:
            if term in jd_lower:
                found_positive.append(term)
        
        return found_positive
    
    def is_sponsorship_friendly_country(self, country: str) -> bool:
        """Check if country commonly offers tech visa sponsorship"""
        return country.lower() in self.sponsorship_friendly_countries
    
    def analyze_visa_requirements(self, job_description: str, location_info: LocationInfo) -> Dict[str, any]:
        """Comprehensive analysis of visa/work permit requirements"""
        
        restrictive_indicators = self.find_restrictive_indicators(job_description)
        positive_indicators = self.find_positive_indicators(job_description)
        
        # Determine if local work permit is required
        required_local_permit = len(restrictive_indicators) > 0
        
        # Determine if sponsorship is offered
        sponsorship_offered = len(positive_indicators) > 0
        
        # Check location compatibility
        is_same_country = location_info.country.lower() == self.applicant_country
        is_remote_friendly = location_info.is_remote
        is_sponsorship_friendly = self.is_sponsorship_friendly_country(location_info.country)
        
        # Overall location compatibility logic
        location_compatible = (
            is_same_country or 
            is_remote_friendly or 
            (is_sponsorship_friendly and sponsorship_offered) or
            (not required_local_permit and is_sponsorship_friendly)
        )
        
        return {
            'required_local_permit': required_local_permit,
            'sponsorship_offered': sponsorship_offered,
            'location_compatible': location_compatible,
            'restrictive_indicators': restrictive_indicators,
            'positive_indicators': positive_indicators,
            'is_same_country': is_same_country,
            'is_remote_friendly': is_remote_friendly,
            'is_sponsorship_friendly_country': is_sponsorship_friendly,
            'applicant_country': settings.APPLICANT_COUNTRY,
            'job_country': location_info.country
        }


class JobFilter:
    """Main job filtering class combining all filtering logic"""
    
    def __init__(self):
        self.work_permit_analyzer = WorkPermitAnalyzer()
    
    def should_ignore_job(self, job_title: str, company_name: str, location: str, 
                         job_description: str) -> FilterDecision:
        """
        Determine if a job should be ignored based on location and work permit requirements
        This runs AFTER role detection has confirmed we want this type of job
        """
        
        # Extract location information
        location_info = self.work_permit_analyzer.extract_location_info(location, job_description)
        
        # Analyze visa requirements
        visa_analysis = self.work_permit_analyzer.analyze_visa_requirements(job_description, location_info)
        
        # Decision logic
        should_ignore = False
        reason = ""
        
        if not visa_analysis['location_compatible']:
            if visa_analysis['required_local_permit'] and not visa_analysis['sponsorship_offered']:
                should_ignore = True
                reason = "work-permit-only"
            elif not visa_analysis['is_same_country'] and not visa_analysis['is_remote_friendly'] and not visa_analysis['is_sponsorship_friendly_country']:
                should_ignore = True
                reason = "location-incompatible"
        
        # Log the decision
        if should_ignore:
            logger.info(f"Ignoring job '{job_title}' at {company_name}: {reason}")
            logger.debug(f"Location analysis: {location_info}")
            logger.debug(f"Visa analysis: {visa_analysis}")
        else:
            logger.info(f"Job '{job_title}' at {company_name} passed location filter")
        
        return FilterDecision(
            should_stop=should_ignore,
            reason=reason,
            details={
                'location_info': location_info._asdict(),
                'visa_analysis': visa_analysis,
                'filter_criteria': {
                    'applicant_country': settings.APPLICANT_COUNTRY,
                    'restrictive_terms_found': len(visa_analysis['restrictive_indicators']),
                    'positive_terms_found': len(visa_analysis['positive_indicators'])
                }
            }
        )
    
    def get_filter_summary(self, job_title: str, company_name: str, location: str, 
                          job_description: str) -> Dict[str, any]:
        """Get detailed filter analysis without making a decision"""
        location_info = self.work_permit_analyzer.extract_location_info(location, job_description)
        visa_analysis = self.work_permit_analyzer.analyze_visa_requirements(job_description, location_info)
        
        return {
            'job_info': {
                'title': job_title,
                'company': company_name,
                'location': location
            },
            'location_analysis': location_info._asdict(),
            'visa_analysis': visa_analysis,
            'recommendation': 'proceed' if visa_analysis['location_compatible'] else 'ignore'
        }


# Factory function for easy access
def create_job_filter() -> JobFilter:
    """Create a configured job filter instance"""
    return JobFilter()


# Convenience function for quick filtering
def check_work_permit_compatibility(job_description: str, location: str) -> FilterDecision:
    """Quick function to check work permit compatibility"""
    job_filter = create_job_filter()
    return job_filter.should_ignore_job("", "", location, job_description)


# Validation function for configuration
def validate_filter_configuration() -> List[str]:
    """Validate filter configuration and return any issues"""
    issues = []
    
    if not settings.APPLICANT_COUNTRY:
        issues.append("APPLICANT_COUNTRY not configured")
    
    if not settings.RESTRICTIVE_LOCAL_TERMS:
        issues.append("No restrictive terms configured")
    
    if not settings.POSITIVE_SPONSORSHIP_TERMS:
        issues.append("No positive sponsorship terms configured")
    
    # Test the analyzer
    try:
        analyzer = WorkPermitAnalyzer()
        test_location = LocationInfo("Test Country", "Test City", "Test Region", False)
        analyzer.analyze_visa_requirements("test description", test_location)
    except Exception as e:
        issues.append(f"Filter initialization failed: {e}")
    
    return issues