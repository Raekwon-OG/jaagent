"""
Job scraping utilities for extracting job postings from various sources
"""
import csv
import json
import logging
import re
import time
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from urllib.parse import urlparse, urljoin
import hashlib
import sys

try:
    import requests
    from bs4 import BeautifulSoup
    SCRAPING_AVAILABLE = True
except ImportError:
    SCRAPING_AVAILABLE = False

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

from config import settings

logger = logging.getLogger(__name__)

class JobScraper:
    """Scrapes job postings from various job sites"""
    
    def __init__(self):
        if not SCRAPING_AVAILABLE:
            raise ImportError("Scraping dependencies not available. Install: pip install requests beautifulsoup4")
        
        self.job_sources_file = Path(settings.JOB_SOURCES_CSV)
        self.max_scrape_limit = settings.MAX_SCRAPE_LIMIT
        # multiplier determines how many candidates to inspect per source (default 3)
        self.per_source_multiplier = getattr(settings, "SCRAPE_SOURCE_MULTIPLIER", 3)
        self.scraped_count = 0
        
        # Setup session with headers to avoid blocking
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        logger.info("Job scraper initialized")
    
    def scrape_jobs_from_sources(self) -> List[Dict[str, Any]]:
        """
        Scrape jobs from configured sources or fallback to remote job providers.
        If no CSV sources and running in a TTY, prompt user for fallback mode.
        """
        
        logger.info("Starting job scraping from configured sources...")
        
        all_jobs = []
        
        try:
            # Try to load custom sources from CSV
            job_sources = self._load_job_sources()
            
            if job_sources:
                logger.info(f"Found {len(job_sources)} custom job sources")
                
                for source in job_sources:
                    if self.scraped_count >= self.max_scrape_limit:
                        logger.info(f"Reached scraping limit of {self.max_scrape_limit}")
                        break
                    
                    site_jobs = self._scrape_from_source(source)
                    all_jobs.extend(site_jobs)
                    
                    # Small delay between sources
                    time.sleep(2)
            
            else:
                # No custom sources: interactive selection if TTY, otherwise default to multi fallback
                mode = "multi"
                if sys.stdin.isatty():
                    try:
                        print("\nNo job sources configured. Choose fallback source:")
                        print("  1) Multi (RemoteOK then WeWorkRemotely)")
                        print("  2) RemoteOK only")
                        print("  3) WeWorkRemotely only")
                        choice = input("Select option [1-3] (default 1): ").strip()
                        if choice == "2":
                            mode = "remoteok"
                        elif choice == "3":
                            mode = "weworkremotely"
                    except Exception:
                        mode = "multi"
                all_jobs.extend(self._scrape_remote_jobs_fallback(mode=mode))
            
            # Remove duplicates and validate jobs
            unique_jobs = self._deduplicate_jobs(all_jobs)
            validated_jobs = self._validate_scraped_jobs(unique_jobs)
            
            logger.info(f"Successfully scraped {len(validated_jobs)} unique jobs")
            
            return validated_jobs
            
        except Exception as e:
            logger.error(f"Error in job scraping: {e}")
            return []
    
    def _load_job_sources(self) -> List[Dict[str, str]]:
        """Load job sources from CSV file"""
        
        if not self.job_sources_file.exists():
            logger.info(f"Job sources file not found: {self.job_sources_file}")
            return []
        
        try:
            sources = []
            
            with open(self.job_sources_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                
                for row in reader:
                    if row.get('site_name') and row.get('base_url'):
                        sources.append({
                            'site_name': row['site_name'].strip(),
                            'base_url': row['base_url'].strip(),
                            'search_params': row.get('search_params', '').strip()
                        })
            
            logger.info(f"Loaded {len(sources)} job sources from CSV")
            return sources
            
        except Exception as e:
            logger.error(f"Error loading job sources: {e}")
            return []
    
    def _scrape_from_source(self, source: Dict[str, str]) -> List[Dict[str, Any]]:
        """Scrape jobs from a specific source"""
        
        site_name = source['site_name']
        base_url = source['base_url']
        
        logger.info(f"Scraping jobs from {site_name}...")
        
        try:
            # Different scraping strategies based on site
            if 'indeed' in site_name.lower():
                 return self._scrape_indeed_jobs(base_url, source.get('search_params', ''))
            elif 'remoteok' in site_name.lower() or 'remote ok' in site_name.lower():
                return self._scrape_remoteok_jobs(base_url)
            elif 'weworkremotely' in site_name.lower() or 'we work remotely' in site_name.lower() or 'wework' in site_name.lower():
                return self._scrape_weworkremotely_jobs(base_url)
            else:
                 # Generic scraping approach
                 return self._scrape_generic_jobs(base_url, source.get('search_params', ''))
                 
        except Exception as e:
             logger.error(f"Error scraping from {site_name}: {e}")
             return []
    
    def _scrape_remote_jobs_fallback(self, mode: str = "multi") -> List[Dict[str, Any]]:
        """Fallback: prefer RemoteOK (API) then WeWorkRemotely (scrape) to reach max_scrape_limit.
        mode: "multi" | "remoteok" | "weworkremotely"
        """
        logger.info("Using remote jobs fallback (mode=%s)", mode)
        jobs: List[Dict[str, Any]] = []
        # candidate_count to inspect per source
        candidate_count = self.max_scrape_limit * max(1, int(self.per_source_multiplier))
        
        # Try RemoteOK first if selected or multi
        if mode in ("multi", "remoteok"):
            try:
                jobs.extend(self._scrape_remoteok_jobs(candidate_limit=candidate_count))
            except Exception as e:
                logger.debug(f"RemoteOK fallback failed: {e}")
        
        # If we haven't hit the limit and either multi or weworkremotely specifically selected, try WWR
        if self.scraped_count < self.max_scrape_limit and mode in ("multi", "weworkremotely"):
            try:
                jobs.extend(self._scrape_weworkremotely_jobs(candidate_limit=candidate_count))
            except Exception as e:
                logger.debug(f"WeWorkRemotely fallback failed: {e}")
        return jobs
    
    def _scrape_indeed_jobs(self, base_url: str, search_params: str) -> List[Dict[str, Any]]:
        """Scrape jobs from Indeed"""
        
        logger.info("Scraping Indeed jobs...")
        
        jobs = []
        
        try:
            # Parse search parameters
            params = self._parse_search_params(search_params)
            
            # Make request to Indeed
            response = self.session.get(base_url, params=params, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find job listings (Indeed structure)
            job_cards = soup.find_all('div', class_=['job_seen_beacon', 'slider_container'])
            
            for card in job_cards:
                if self.scraped_count >= self.max_scrape_limit:
                    break
                
                try:
                    job = self._extract_indeed_job_data(card, base_url)
                    if job:
                        jobs.append(job)
                        self.scraped_count += 1
                        
                except Exception as e:
                    logger.debug(f"Error extracting job from Indeed card: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"Error scraping Indeed: {e}")
        
        logger.info(f"Scraped {len(jobs)} jobs from Indeed")
        return jobs
    
    def _scrape_remoteok_jobs(self, base_url: str = None, candidate_limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Scrape jobs from RemoteOK using their API
        
        candidate_limit: how many RemoteOK items to inspect (not how many to append).
        """
        
        logger.info("Scraping RemoteOK jobs...")
        
        jobs = []
        
        try:
            # RemoteOK has a public JSON API
            api_url = "https://remoteok.com/api/?location=Worldwide"
            
            # Add headers to mimic browser
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
                'Accept': 'application/json, text/html',
                'Accept-Language': 'en-GB,en;q=0.9'
            }
            
            response = self.session.get(api_url, headers=headers, timeout=15)
            response.raise_for_status()
            
            job_data = response.json()
            
            # First item is metadata/legal notice, skip it
            if isinstance(job_data, list) and len(job_data) > 0:
                if 'legal' in job_data[0] or 'last_updated' in job_data[0]:
                    job_data = job_data[1:]  # Skip metadata
            
            logger.info(f"Found {len(job_data)} jobs from RemoteOK API")
            
            # Determine how many candidates to inspect
            if candidate_limit is None:
                candidate_limit = self.max_scrape_limit * max(1, int(self.per_source_multiplier))
            candidate_limit = min(len(job_data), int(candidate_limit))
            
            inspected = 0
            for item in job_data:
                if inspected >= candidate_limit:
                    break
                inspected += 1
                
                # stop early if we've already collected enough valid jobs
                if self.scraped_count >= self.max_scrape_limit:
                    break
                
                try:
                    job = self._extract_remoteok_job_data(item)
                    if job:
                        jobs.append(job)
                        self.scraped_count += 1
                        
                except Exception as e:
                    logger.debug(f"Error extracting RemoteOK job: {e}")
                    continue
            
            logger.info(f"Inspected {inspected} RemoteOK candidates, appended {len(jobs)} jobs")
            
        except Exception as e:
            logger.error(f"Error scraping RemoteOK: {e}")
        
        logger.info(f"Successfully scraped {len(jobs)} jobs from RemoteOK")
        return jobs
    
    def _scrape_weworkremotely_jobs(self, base_url: str = None, candidate_limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Scrape jobs from We Work Remotely
        
        candidate_limit: number of list items to inspect (not guaranteed appends).
        """
        
        logger.info("Scraping We Work Remotely jobs...")
        
        jobs = []
        
        try:
            # We Work Remotely URL for worldwide remote jobs
            wwr_url = "https://weworkremotely.com/100-percent-remote-jobs"
            
            # Headers to mimic browser
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/137.0.0.0',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-GB,en;q=0.9',
                'Referer': 'https://www.google.com/'
            }
            
            response = self.session.get(wwr_url, headers=headers, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Determine candidate limit
            if candidate_limit is None:
                candidate_limit = self.max_scrape_limit * max(1, int(self.per_source_multiplier))
            job_items = soup.find_all('li', class_=re.compile(r'listing|job|feature|new-listing'), limit=int(candidate_limit))
            logger.info(f"Found {len(job_items)} potential listings on WeWorkRemotely (limited to {candidate_limit})")
            
            inspected = 0
            for item in job_items:
                if inspected >= int(candidate_limit):
                    break
                inspected += 1
                
                if self.scraped_count >= self.max_scrape_limit:
                    break
                
                try:
                    job = self._extract_weworkremotely_job_data(item)
                    if job:
                        jobs.append(job)
                        self.scraped_count += 1
                except Exception as e:
                    logger.debug(f"Error extracting WWR job data: {e}")
                    continue
            
            logger.info(f"Inspected {inspected} WWR candidates, appended {len(jobs)} jobs")
            
        except Exception as e:
            logger.error(f"Error scraping We Work Remotely: {e}")
        
        logger.info(f"Successfully scraped {len(jobs)} jobs from We Work Remotely")
        return jobs
    
    def _extract_weworkremotely_job_data(self, job_item) -> Optional[Dict[str, Any]]:
        """Extract job data from We Work Remotely listing"""
        
        try:
            # Find the link element
            link_elem = job_item.find('a')
            if not link_elem:
                return None
            
            job_url = f"https://weworkremotely.com{link_elem.get('href', '')}"
            
            # Find the new-listing div
            listing_div = job_item.find('div', class_='new-listing')
            if not listing_div:
                return None
            
            # Extract job title
            title_elem = listing_div.find('h3', class_='new-listing__header__title')
            job_title = title_elem.get_text().strip() if title_elem else 'Unknown Title'
            
            # Extract company name
            company_elem = listing_div.find('p', class_='new-listing__company-name')
            company_name = 'Unknown Company'
            if company_elem:
                # Remove the icon and get just the text
                company_text = company_elem.get_text().strip()
                # Clean up any extra whitespace
                company_name = ' '.join(company_text.split())
            
            # Extract location/headquarters
            location_elem = listing_div.find('p', class_='new-listing__company-headquarters')
            location = 'Remote'
            if location_elem:
                location_text = location_elem.get_text().strip()
                # Remove the location icon and clean up
                location = ' '.join(location_text.split())
            
            # Extract categories (job type, salary, etc.)
            categories_div = listing_div.find('div', class_='new-listing__categories')
            employment_type = 'Full-Time'
            salary_range = ''
            job_location = 'Anywhere in the World'
            
            if categories_div:
                category_items = categories_div.find_all('p', class_='new-listing__categories__category')
                for cat in category_items:
                    cat_text = cat.get_text().strip()
                    # Check if it's a salary range
                    if '$' in cat_text or 'USD' in cat_text:
                        salary_range = cat_text
                    # Check if it's employment type
                    elif 'time' in cat_text.lower() or 'contract' in cat_text.lower():
                        employment_type = cat_text
                    # Check if it's location
                    elif 'anywhere' in cat_text.lower() or 'world' in cat_text.lower():
                        job_location = cat_text
            
            # Generate unique job ID
            job_id = self._generate_job_id(job_title, company_name, 'wwr')
            
            # Build job description placeholder (would need to visit job page for full description)
            job_description = f"Remote position: {job_title} at {company_name}. Location: {job_location}. Visit the job posting for full details."
            
            return {
                'job_id': job_id,
                'job_title': job_title,
                'company_name': company_name,
                'company_address': job_item.get('company_logo', ''),
                'job_link': job_url,
                'location': job_location,
                'country': 'Remote',
                'employment_type': employment_type,
                'posted_date': '',
                'job_description': job_description,
                'salary_range': salary_range
            }
            
        except Exception as e:
            logger.debug(f"Error extracting We Work Remotely job data: {e}")
            return None
    
    def _scrape_generic_jobs(self, base_url: str, search_params: str) -> List[Dict[str, Any]]:
        """Generic job scraping for unknown sites"""
        
        logger.info(f"Using generic scraping for {base_url}")
        
        jobs = []
        
        try:
            params = self._parse_search_params(search_params)
            
            response = self.session.get(base_url, params=params, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Look for common job listing patterns
            potential_jobs = soup.find_all(['div', 'article', 'li'], class_=re.compile(r'job|listing|card'))
            
            for element in potential_jobs:
                if self.scraped_count >= self.max_scrape_limit:
                    break
                
                try:
                    job = self._extract_generic_job_data(element, base_url)
                    if job:
                        jobs.append(job)
                        self.scraped_count += 1
                        
                except Exception as e:
                    logger.debug(f"Error extracting generic job: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"Error in generic scraping: {e}")
        
        logger.info(f"Scraped {len(jobs)} jobs using generic method")
        return jobs
    
    def _parse_search_params(self, search_params: str) -> Dict[str, str]:
        """Parse search parameters string into dictionary"""
        
        params = {}
        
        if not search_params:
            return params
        
        # Handle different formats: "key=value&key2=value2" or "{key: value}"
        if '=' in search_params:
            for param in search_params.split('&'):
                if '=' in param:
                    key, value = param.split('=', 1)
                    params[key.strip()] = value.strip()
        
        return params
    
    def _extract_indeed_job_data(self, card_element, base_url: str) -> Optional[Dict[str, Any]]:
        """Extract job data from Indeed job card"""
        
        try:
            # Extract title
            title_elem = card_element.find('h2') or card_element.find('a', class_=re.compile(r'title'))
            title = title_elem.get_text().strip() if title_elem else 'Unknown Title'
            
            # Extract company
            company_elem = card_element.find('span', class_=re.compile(r'company')) or card_element.find('div', class_=re.compile(r'company'))
            company = company_elem.get_text().strip() if company_elem else 'Unknown Company'
            
            # Extract location
            location_elem = card_element.find('div', class_=re.compile(r'location'))
            location = location_elem.get_text().strip() if location_elem else 'Unknown Location'
            
            # Extract job link
            link_elem = card_element.find('a')
            job_link = ''
            if link_elem and link_elem.get('href'):
                job_link = urljoin(base_url, link_elem['href'])
            
            # Generate job ID
            job_id = self._generate_job_id(title, company, 'indeed')
            
            return {
                'job_id': job_id,
                'job_title': title,
                'company_name': company,
                'company_address': location,
                'job_link': job_link,
                'location': location,
                'country': self._extract_country_from_location(location),
                'employment_type': 'Full-time',
                'posted_date': '',
                'job_description': f'Job posting from Indeed for {title} at {company}',
                'salary_range': ''
            }
            
        except Exception as e:
            logger.debug(f"Error extracting Indeed job data: {e}")
            return None
    
    def _extract_remoteok_job_data(self, job_item: Dict) -> Optional[Dict[str, Any]]:
        """Extract job data from RemoteOK API response"""
        
        try:
            # RemoteOK API structure
            job_id = self._generate_job_id(
                job_item.get('position', 'Unknown'),
                job_item.get('company', 'Unknown'),
                'remoteok'
            )
            
            return {
                'job_id': job_id,
                'job_title': job_item.get('position', 'Unknown Title'),
                'company_name': job_item.get('company', 'Unknown Company'),
                'company_address': job_item.get('company_logo', ''),
                'job_link': f"https://remoteok.io/remote-jobs/{job_item.get('id', '')}",
                'location': 'Remote',
                'country': 'Remote',
                'employment_type': 'Remote',
                'posted_date': job_item.get('date', ''),
                'job_description': job_item.get('description', ''),
                'salary_range': f"${job_item.get('salary_min', '')}-${job_item.get('salary_max', '')}" if job_item.get('salary_min') else ''
            }
            
        except Exception as e:
            logger.debug(f"Error extracting RemoteOK job data: {e}")
            return None
    
    def _extract_generic_job_data(self, element, base_url: str) -> Optional[Dict[str, Any]]:
        """Extract job data using generic patterns"""
        
        try:
            # Try to find title
            title_elem = (element.find('h1') or element.find('h2') or element.find('h3') or 
                         element.find('a') or element.find(class_=re.compile(r'title|job-title')))
            title = title_elem.get_text().strip() if title_elem else 'Generic Job'
            
            # Try to find company
            company_elem = element.find(class_=re.compile(r'company|employer'))
            company = company_elem.get_text().strip() if company_elem else 'Unknown Company'
            
            # Try to find location
            location_elem = element.find(class_=re.compile(r'location|address'))
            location = location_elem.get_text().strip() if location_elem else 'Unknown Location'
            
            # Try to find link
            link_elem = element.find('a')
            job_link = ''
            if link_elem and link_elem.get('href'):
                job_link = urljoin(base_url, link_elem['href'])
            
            # Only return if we found meaningful data
            if len(title) > 3 and len(company) > 3:
                job_id = self._generate_job_id(title, company, 'generic')
                
                return {
                    'job_id': job_id,
                    'job_title': title,
                    'company_name': company,
                    'company_address': location,
                    'job_link': job_link or base_url,
                    'location': location,
                    'country': self._extract_country_from_location(location),
                    'employment_type': 'Full-time',
                    'posted_date': '',
                    'job_description': f'Job posting scraped from {urlparse(base_url).netloc}',
                    'salary_range': ''
                }
            
            return None
            
        except Exception as e:
            logger.debug(f"Error extracting generic job data: {e}")
            return None
    
    def _generate_job_id(self, title: str, company: str, source: str) -> str:
        """Generate unique job ID from title, company, and source"""
        
        # Create a hash from the combination
        content = f"{title}_{company}_{source}".lower()
        hash_obj = hashlib.md5(content.encode())
        
        return f"{source}_{hash_obj.hexdigest()[:8]}"
    
    def _extract_country_from_location(self, location: str) -> str:
        """Extract country from location string"""
        
        location_lower = location.lower()
        
        # Common country patterns
        country_mapping = {
            'usa': 'United States',
            'us': 'United States',
            'united states': 'United States',
            'uk': 'United Kingdom',
            'united kingdom': 'United Kingdom',
            'canada': 'Canada',
            'australia': 'Australia',
            'germany': 'Germany',
            'france': 'France',
            'netherlands': 'Netherlands',
            'singapore': 'Singapore',
            'remote': 'Remote'
        }
        
        for key, country in country_mapping.items():
            if key in location_lower:
                return country
        
        # If no match, try to extract last part after comma
        parts = location.split(',')
        if len(parts) > 1:
            potential_country = parts[-1].strip().title()
            if len(potential_country) > 2:
                return potential_country
        
        return 'Unknown'
    
    def _deduplicate_jobs(self, jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate jobs based on job_id and title+company combination"""
        
        seen_ids = set()
        seen_combinations = set()
        unique_jobs = []
        
        for job in jobs:
            job_id = job.get('job_id', '')
            title = job.get('job_title', '').lower().strip()
            company = job.get('company_name', '').lower().strip()
            combination = f"{title}_{company}"
            
            if job_id not in seen_ids and combination not in seen_combinations:
                seen_ids.add(job_id)
                seen_combinations.add(combination)
                unique_jobs.append(job)
        
        logger.info(f"Deduplicated {len(jobs)} jobs down to {len(unique_jobs)} unique jobs")
        return unique_jobs
    
    def _validate_scraped_jobs(self, jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Validate scraped jobs and filter out invalid ones"""
        
        valid_jobs = []
        
        for job in jobs:
            # Check required fields
            if (job.get('job_title') and len(job.get('job_title', '')) > 2 and
                job.get('company_name') and len(job.get('company_name', '')) > 2 and
                job.get('job_id')):
                
                # Clean up the data
                job['job_title'] = job['job_title'].strip()
                job['company_name'] = job['company_name'].strip()
                job['location'] = job.get('location', '').strip()
                
                # Ensure all required fields exist
                required_fields = [
                    'job_id', 'job_title', 'company_name', 'job_link', 'location', 
                    'country', 'job_description'
                ]
                
                for field in required_fields:
                    if field not in job:
                        job[field] = ''
                
                valid_jobs.append(job)
        
        logger.info(f"Validated {len(valid_jobs)} out of {len(jobs)} scraped jobs")
        return valid_jobs
    
    def scrape_job_from_url(self, job_url: str) -> Optional[Dict[str, Any]]:
        """Scrape a single job from a specific URL"""
        
        logger.info(f"Scraping single job from URL: {job_url}")
        
        try:
            response = self.session.get(job_url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Try to extract job data using generic patterns
            job_data = {
                'job_id': self._generate_job_id('url_job', 'unknown', 'manual'),
                'job_title': self._extract_title_from_page(soup),
                'company_name': self._extract_company_from_page(soup),
                'company_address': '',
                'job_link': job_url,
                'location': self._extract_location_from_page(soup),
                'country': 'Unknown',
                'employment_type': 'Full-time',
                'posted_date': '',
                'job_description': self._extract_description_from_page(soup),
                'salary_range': ''
            }
            
            # Set country based on location
            job_data['country'] = self._extract_country_from_location(job_data['location'])
            
            # Validate the extracted data
            if job_data['job_title'] and job_data['company_name']:
                logger.info(f"Successfully scraped job: {job_data['job_title']} at {job_data['company_name']}")
                return job_data
            else:
                logger.warning("Could not extract sufficient job data from URL")
                return None
                
        except Exception as e:
            logger.error(f"Error scraping job from URL {job_url}: {e}")
            return None
    
    def _extract_title_from_page(self, soup: BeautifulSoup) -> str:
        """Extract job title from page"""
        
        # Try multiple selectors
        selectors = [
            'h1',
            '.job-title',
            '.jobTitle',
            '[class*="title"]',
            'title'
        ]
        
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                title = element.get_text().strip()
                if len(title) > 3 and len(title) < 100:
                    return title
        
        return 'Unknown Job Title'
    
    def _extract_company_from_page(self, soup: BeautifulSoup) -> str:
        """Extract company name from page"""
        
        selectors = [
            '.company-name',
            '.companyName',
            '[class*="company"]',
            '[data-testid*="company"]'
        ]
        
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                company = element.get_text().strip()
                if len(company) > 2 and len(company) < 50:
                    return company
        
        return 'Unknown Company'
    
    def _extract_location_from_page(self, soup: BeautifulSoup) -> str:
        """Extract location from page"""
        
        selectors = [
            '.location',
            '.job-location',
            '[class*="location"]',
            '[data-testid*="location"]'
        ]
        
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                location = element.get_text().strip()
                if len(location) > 2:
                    return location
        
        return 'Unknown Location'
    
    def _extract_description_from_page(self, soup: BeautifulSoup) -> str:
        """Extract job description from page"""
        
        selectors = [
            '.job-description',
            '.jobDescription',
            '[class*="description"]',
            '.content',
            'main',
            '.job-details'
        ]
        
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                # Get text and clean it up
                description = element.get_text()
                description = re.sub(r'\s+', ' ', description).strip()
                if len(description) > 100:  # Reasonable description length
                    return description[:5000]  # Limit length
        
        return 'Job description not available'
    
    def get_scraping_stats(self) -> Dict[str, Any]:
        """Get statistics about scraping session"""
        
        return {
            'scraped_count': self.scraped_count,
            'max_limit': self.max_scrape_limit,
            'sources_file_exists': self.job_sources_file.exists(),
            'sources_loaded': len(self._load_job_sources()) if self.job_sources_file.exists() else 0
        }


# Factory function
def create_job_scraper() -> JobScraper:
    """Create a configured job scraper instance"""
    return JobScraper()


# Global scraper instance
_global_scraper: Optional[JobScraper] = None

def get_global_scraper() -> JobScraper:
    """Get or create the global job scraper instance"""
    global _global_scraper
    if _global_scraper is None:
        _global_scraper = create_job_scraper()
    return _global_scraper


# Convenience functions
def scrape_jobs_batch() -> List[Dict[str, Any]]:
    """Quick function to scrape jobs from configured sources"""
    scraper = get_global_scraper()
    return scraper.scrape_jobs_from_sources()

def scrape_single_job(job_url: str) -> Optional[Dict[str, Any]]:
    """Quick function to scrape a single job from URL"""
    scraper = get_global_scraper()
    return scraper.scrape_job_from_url(job_url)

def create_sample_job_sources_csv():
    """Create a sample job sources CSV file"""
    
    sample_sources = [
        {
            'site_name': 'Indeed',
            'base_url': 'https://indeed.com/jobs',
            'search_params': 'q=software+engineer&l=Remote'
        },
        {
            'site_name': 'RemoteOK',
            'base_url': 'https://remoteok.io',
            'search_params': ''
        },
        {
            'site_name': 'AngelList',
            'base_url': 'https://angel.co/jobs',
            'search_params': 'keyword=developer'
        }
    ]
    
    csv_path = Path(settings.JOB_SOURCES_CSV)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['site_name', 'base_url', 'search_params'])
        writer.writeheader()
        writer.writerows(sample_sources)
    
    logger.info(f"Created sample job sources CSV at: {csv_path}")
    return csv_path