# Save as robust_search.py and run it

import sys
import subprocess
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed

# Install required packages
required_packages = [
    'ddgs', 'beautifulsoup4', 'requests', 'python-dateutil', 
    'colorama', 'wizsearch', 'zero-api-key-web-search'
]

for package in required_packages:
    try:
        __import__(package.replace('-', '_'))
    except ImportError:
        print(f"Installing {package}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])

from ddgs import DDGS
from bs4 import BeautifulSoup
import requests
from dateutil import parser
from colorama import init, Fore, Style

# Try importing optional search libraries
try:
    from wizsearch import DuckDuckGoSearch, DuckDuckGoSearchConfig
    WIZSEARCH_AVAILABLE = True
except ImportError:
    WIZSEARCH_AVAILABLE = False
    print(f"{Fore.YELLOW}Note: wizsearch not available - some features limited{Style.RESET_ALL}")

try:
    from zero_api_key_web_search import ZeroSearch
    ZERO_SEARCH_AVAILABLE = True
except ImportError:
    ZERO_SEARCH_AVAILABLE = False
    print(f"{Fore.YELLOW}Note: zero-api-key-web-search not available{Style.RESET_ALL}")

# Initialize colorama for colored output
init(autoreset=True)


class SearchProvider(Enum):
    """Available search providers"""
    DUCKDUCKGO = "duckduckgo"
    WIZSEARCH = "wizsearch"
    ZERO_SEARCH = "zero_search"
    BING = "bing"
    BRAVE = "brave"  # Requires API key


@dataclass
class SearchResult:
    """Base class for all search results"""
    title: str
    url: str
    snippet: str
    source: str
    provider: str
    timestamp: Optional[datetime] = None
    relevance_score: float = 0.0


@dataclass
class JobResult(SearchResult):
    """Job-specific search result"""
    company: str = ""
    location: str = ""
    salary: Optional[str] = None
    job_type: str = ""
    posted_date: Optional[str] = None


class MultiProviderSearch:
    """Search engine with multiple fallback providers for reliability"""
    
    def __init__(self, preferred_providers: List[SearchProvider] = None):
        self.providers = preferred_providers or [
            SearchProvider.DUCKDUCKGO,
            SearchProvider.WIZSEARCH,
            SearchProvider.ZERO_SEARCH
        ]
        self.active_provider = None
        self.provider_health = {p: True for p in self.providers}
        
    def _search_with_ddgs(self, query: str, limit: int = 10, search_type: str = "web") -> List[Dict]:
        """Search using DDGS (DuckDuckGo)"""
        try:
            with DDGS() as ddgs:
                if search_type == "images":
                    results = list(ddgs.images(query, max_results=limit))
                    return [{
                        'title': r.get('title', ''),
                        'url': r.get('image', ''),
                        'snippet': f"Source: {r.get('source', 'Unknown')} | Dimensions: {r.get('width', 'N/A')}x{r.get('height', 'N/A')}",
                        'source': 'DDGS Image Search'
                    } for r in results]
                elif search_type == "news":
                    results = list(ddgs.news(query, max_results=limit))
                    return [{
                        'title': r.get('title', ''),
                        'url': r.get('url', ''),
                        'snippet': r.get('body', '')[:300],
                        'source': r.get('source', 'DDGS News')
                    } for r in results]
                else:
                    results = list(ddgs.text(query, max_results=limit))
                    return [{
                        'title': r.get('title', ''),
                        'url': r.get('href', ''),
                        'snippet': r.get('body', '')[:300],
                        'source': 'DDGS Web Search'
                    } for r in results]
        except Exception as e:
            print(f"{Fore.YELLOW}DDGS search failed: {e}{Style.RESET_ALL}")
            return []
    
    def _search_with_wizsearch(self, query: str, limit: int = 10) -> List[Dict]:
        """Search using WizSearch (unified search interface)"""
        if not WIZSEARCH_AVAILABLE:
            return []
        
        try:
            # Run async search in sync context
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            config = DuckDuckGoSearchConfig(max_results=limit)
            searcher = DuckDuckGoSearch(config=config)
            results = loop.run_until_complete(searcher.search(query))
            loop.close()
            
            return [{
                'title': r.title if hasattr(r, 'title') else '',
                'url': r.url if hasattr(r, 'url') else '',
                'snippet': r.snippet if hasattr(r, 'snippet') else '',
                'source': 'WizSearch'
            } for r in results]
        except Exception as e:
            print(f"{Fore.YELLOW}WizSearch failed: {e}{Style.RESET_ALL}")
            return []
    
    def _search_with_zero_search(self, query: str, limit: int = 10) -> List[Dict]:
        """Search using Zero-API-Key Web Search"""
        if not ZERO_SEARCH_AVAILABLE:
            return []
        
        try:
            # Use the CLI via subprocess or direct import
            result = subprocess.run(
                ['zero-search', query, '--json', '--limit', str(limit)],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                results = data.get('results', [])
                return [{
                    'title': r.get('title', ''),
                    'url': r.get('url', ''),
                    'snippet': r.get('snippet', '')[:300],
                    'source': 'Zero-Search'
                } for r in results]
            return []
        except Exception as e:
            print(f"{Fore.YELLOW}Zero-Search failed: {e}{Style.RESET_ALL}")
            return []
    
    def _search_with_bing(self, query: str, limit: int = 10) -> List[Dict]:
        """Search using Bing (requires subscription key)"""
        # Note: Bing requires an API key from Azure Marketplace
        bing_key = os.environ.get('BING_API_KEY', '')
        if not bing_key:
            return []
        
        try:
            url = "https://api.bing.microsoft.com/v7.0/search"
            headers = {"Ocp-Apim-Subscription-Key": bing_key}
            params = {"q": query, "count": limit}
            
            response = requests.get(url, headers=headers, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return [{
                    'title': r.get('name', ''),
                    'url': r.get('url', ''),
                    'snippet': r.get('snippet', '')[:300],
                    'source': 'Bing API'
                } for r in data.get('webPages', {}).get('value', [])]
            return []
        except Exception as e:
            print(f"{Fore.YELLOW}Bing search failed: {e}{Style.RESET_ALL}")
            return []
    
    def search_with_fallback(self, query: str, limit: int = 10, 
                            search_type: str = "web") -> List[Dict]:
        """
        Search using multiple providers with automatic fallback.
        Returns results from the first working provider.
        """
        results = []
        
        for provider in self.providers:
            if not self.provider_health.get(provider, False):
                continue
                
            print(f"{Fore.CYAN}Trying provider: {provider.value}...{Style.RESET_ALL}")
            
            try:
                if provider == SearchProvider.DUCKDUCKGO:
                    results = self._search_with_ddgs(query, limit, search_type)
                elif provider == SearchProvider.WIZSEARCH:
                    results = self._search_with_wizsearch(query, limit)
                elif provider == SearchProvider.ZERO_SEARCH:
                    results = self._search_with_zero_search(query, limit)
                elif provider == SearchProvider.BING:
                    results = self._search_with_bing(query, limit)
                
                if results:
                    self.active_provider = provider
                    print(f"{Fore.GREEN}✓ Success using {provider.value}{Style.RESET_ALL}")
                    return results
                else:
                    print(f"{Fore.YELLOW}✗ No results from {provider.value}{Style.RESET_ALL}")
                    
            except Exception as e:
                print(f"{Fore.RED}✗ {provider.value} failed: {e}{Style.RESET_ALL}")
                self.provider_health[provider] = False
        
        print(f"{Fore.RED}All providers failed. Check your internet connection.{Style.RESET_ALL}")
        return []
    
    def search_parallel(self, query: str, limit: int = 10, 
                       search_type: str = "web") -> List[Dict]:
        """
        Search using multiple providers in parallel and merge results.
        Returns combined unique results from all working providers.
        """
        all_results = []
        seen_urls = set()
        
        def search_with_provider(provider):
            if provider == SearchProvider.DUCKDUCKGO:
                return self._search_with_ddgs(query, limit, search_type)
            elif provider == SearchProvider.WIZSEARCH:
                return self._search_with_wizsearch(query, limit)
            elif provider == SearchProvider.ZERO_SEARCH:
                return self._search_with_zero_search(query, limit)
            elif provider == SearchProvider.BING:
                return self._search_with_bing(query, limit)
            return []
        
        # Run searches in parallel using ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=len(self.providers)) as executor:
            future_to_provider = {
                executor.submit(search_with_provider, p): p 
                for p in self.providers
            }
            
            for future in as_completed(future_to_provider):
                provider = future_to_provider[future]
                try:
                    results = future.result(timeout=30)
                    if results:
                        # Add provider info and deduplicate
                        for r in results:
                            url = r.get('url', '')
                            if url not in seen_urls:
                                seen_urls.add(url)
                                r['provider'] = provider.value
                                all_results.append(r)
                        print(f"{Fore.GREEN}✓ Got {len(results)} results from {provider.value}{Style.RESET_ALL}")
                except Exception as e:
                    print(f"{Fore.YELLOW}✗ {provider.value} failed: {e}{Style.RESET_ALL}")
        
        # Sort by some relevance metric (simple: title length as proxy)
        all_results.sort(key=lambda x: len(x.get('title', '')), reverse=True)
        return all_results[:limit]


class RobustSearchEngine:
    """Enhanced search engine with multi-provider support"""
    
    def __init__(self):
        self.multi_search = MultiProviderSearch()
        
    def search_pdfs(self, keyword: str, limit: int = 10, use_parallel: bool = True) -> List[SearchResult]:
        """Search for PDF files using multiple providers"""
        results = []
        query = f"{keyword} filetype:pdf"
        
        if use_parallel:
            raw_results = self.multi_search.search_parallel(query, limit, "web")
        else:
            raw_results = self.multi_search.search_with_fallback(query, limit, "web")
        
        for r in raw_results:
            if 'pdf' in r.get('url', '').lower():
                results.append(SearchResult(
                    title=r.get('title', 'No title'),
                    url=r.get('url', ''),
                    snippet=r.get('snippet', '')[:200],
                    source=r.get('source', 'Unknown'),
                    provider=r.get('provider', self.multi_search.active_provider.value if self.multi_search.active_provider else 'unknown'),
                    timestamp=self._extract_date(r.get('snippet', ''))
                ))
        
        return results
    
    def search_images(self, keyword: str, limit: int = 10, use_parallel: bool = True) -> List[SearchResult]:
        """Search for images using multiple providers"""
        if use_parallel:
            raw_results = self.multi_search.search_parallel(keyword, limit, "images")
        else:
            raw_results = self.multi_search.search_with_fallback(keyword, limit, "images")
        
        return [SearchResult(
            title=r.get('title', 'No title'),
            url=r.get('url', ''),
            snippet=r.get('snippet', ''),
            source=r.get('source', 'Image Search'),
            provider=r.get('provider', self.multi_search.active_provider.value if self.multi_search.active_provider else 'unknown')
        ) for r in raw_results]
    
    def search_web(self, keyword: str, limit: int = 10, use_parallel: bool = True) -> List[SearchResult]:
        """General web search using multiple providers"""
        if use_parallel:
            raw_results = self.multi_search.search_parallel(keyword, limit, "web")
        else:
            raw_results = self.multi_search.search_with_fallback(keyword, limit, "web")
        
        return [SearchResult(
            title=r.get('title', 'No title'),
            url=r.get('url', ''),
            snippet=r.get('snippet', '')[:300],
            source=r.get('source', 'Web Search'),
            provider=r.get('provider', self.multi_search.active_provider.value if self.multi_search.active_provider else 'unknown'),
            timestamp=self._extract_date(r.get('snippet', ''))
        ) for r in raw_results]
    
    def search_jobs(self, job_title: str, location: str = "", limit: int = 20) -> List[JobResult]:
        """Search for jobs with enhanced parsing"""
        # For jobs, we still primarily use DDGS for better job extraction
        # But we add fallback providers
        jobs = []
        
        queries = [
            f"{job_title} job {location}",
            f"{job_title} hiring {location}",
            f"{job_title} career {location}"
        ]
        
        for query in queries[:2]:
            results = self.multi_search.search_with_fallback(query, limit, "web")
            
            for r in results:
                job = self._extract_job_info(r, job_title, location)
                if job:
                    jobs.append(job)
        
        # Deduplicate by URL
        unique_jobs = []
        seen_urls = set()
        for job in jobs:
            if job.url not in seen_urls:
                seen_urls.add(job.url)
                unique_jobs.append(job)
        
        # Sort by timestamp (newest first)
        unique_jobs.sort(key=lambda x: x.timestamp if x.timestamp else datetime.min, reverse=True)
        
        return unique_jobs[:limit]
    
    def _extract_job_info(self, result: Dict, job_title: str, location: str) -> Optional[JobResult]:
        """Extract job information from search result"""
        title = result.get('title', '')
        url = result.get('url', '')
        snippet = result.get('snippet', '')
        provider = result.get('provider', 'unknown')
        
        # Extract company
        company = self._extract_company(title, snippet)
        
        # Extract location
        job_location = self._extract_location(title, snippet, location)
        
        # Extract salary
        salary = self._extract_salary(snippet)
        
        # Extract job type
        job_type = self._extract_job_type(snippet)
        
        # Extract posted date
        posted_date = self._extract_posted_date(snippet)
        timestamp = self._parse_date_string(posted_date) if posted_date else None
        
        return JobResult(
            title=title[:150],
            url=url,
            snippet=snippet[:300],
            source=f"Job Search via {provider}",
            provider=provider,
            timestamp=timestamp,
            company=company,
            location=job_location,
            salary=salary,
            job_type=job_type,
            posted_date=posted_date
        )
    
    def _extract_company(self, title: str, snippet: str) -> str:
        """Extract company name from job listing"""
        patterns = [
            r'at\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
            r'@\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
            r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:is\s+)?hiring',
            r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+career',
            r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+job'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, f"{title} {snippet}", re.IGNORECASE)
            if match:
                return match.group(1)
        
        return "Company not specified"
    
    def _extract_location(self, title: str, snippet: str, user_location: str) -> str:
        """Extract job location"""
        if user_location:
            return user_location
        
        location_patterns = [
            r'in\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
            r'located\s+in\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
            r'remote|work from home|anywhere',
            r'\(([A-Z]{2})\)',
        ]
        
        for pattern in location_patterns:
            match = re.search(pattern, f"{title} {snippet}", re.IGNORECASE)
            if match:
                if pattern == r'remote|work from home|anywhere':
                    return "Remote"
                return match.group(1)
        
        return "Location not specified"
    
    def _extract_salary(self, text: str) -> Optional[str]:
        """Extract salary information"""
        salary_patterns = [
            r'\$\d{1,3}(?:,\d{3})*(?:-\$\d{1,3}(?:,\d{3})*)?',
            r'\d{1,3}(?:,\d{3})*\s*(?:k|K)\s*(?:-\s*\d{1,3}(?:,\d{3})*\s*(?:k|K))?',
            r'(?:per\s+)?(?:hour|year|month|annum)',
        ]
        
        for pattern in salary_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(0)
        
        return None
    
    def _extract_job_type(self, text: str) -> str:
        """Extract job type"""
        job_types = {
            'full[- ]time': 'Full-time',
            'part[- ]time': 'Part-time',
            'remote': 'Remote',
            'hybrid': 'Hybrid',
            'contract': 'Contract',
            'freelance': 'Freelance',
            'internship': 'Internship',
        }
        
        text_lower = text.lower()
        for pattern, job_type in job_types.items():
            if re.search(pattern, text_lower):
                return job_type
        
        return "Not specified"
    
    def _extract_posted_date(self, text: str) -> Optional[str]:
        """Extract posted date"""
        date_patterns = [
            r'posted\s+(\d+)\s+(day|days|hour|hours|week|weeks|month|months)\s+ago',
            r'(\d+)\s+(day|days|hour|hours|week|weeks|month|months)\s+ago',
            r'just\s+posted',
            r'(today|yesterday)',
            r'(\d{1,2}/\d{1,2}/\d{2,4})',
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if pattern == r'just\s+posted':
                    return "Just posted"
                elif pattern == r'(today|yesterday)':
                    return match.group(1)
                else:
                    return match.group(0)
        
        return None
    
    def _parse_date_string(self, date_str: str) -> Optional[datetime]:
        """Parse date string to datetime"""
        try:
            if 'day' in date_str:
                days = int(re.search(r'(\d+)', date_str).group(1))
                return datetime.now() - timedelta(days=days)
            elif 'hour' in date_str:
                hours = int(re.search(r'(\d+)', date_str).group(1))
                return datetime.now() - timedelta(hours=hours)
            elif 'week' in date_str:
                weeks = int(re.search(r'(\d+)', date_str).group(1))
                return datetime.now() - timedelta(weeks=weeks)
            elif date_str.lower() == 'today':
                return datetime.now()
            elif date_str.lower() == 'yesterday':
                return datetime.now() - timedelta(days=1)
            else:
                return parser.parse(date_str, fuzzy=True)
        except:
            return None
    
    def _extract_date(self, text: str) -> Optional[datetime]:
        """Extract date from text"""
        date_patterns = [
            r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},?\s+\d{4}\b',
            r'\b\d{1,2}/\d{1,2}/\d{2,4}\b',
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    return parser.parse(match.group(0), fuzzy=True)
                except:
                    continue
        return None


class SearchRenderer:
    """Handle formatted output of search results"""
    
    @staticmethod
    def render_pdfs(results: List[SearchResult]):
        """Render PDF search results"""
        if not results:
            print(f"{Fore.YELLOW}No PDF results found.{Style.RESET_ALL}")
            return
        
        print(f"\n{Fore.CYAN}{'='*80}{Style.RESET_ALL}")
        print(f"{Fore.GREEN}📄 PDF SEARCH RESULTS ({len(results)} found){Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")
        
        for idx, pdf in enumerate(results, 1):
            print(f"{Fore.YELLOW}{idx}. {pdf.title[:100]}{Style.RESET_ALL}")
            print(f"   {Fore.BLUE}🔗 URL: {pdf.url[:80]}{Style.RESET_ALL}")
            print(f"   {Fore.WHITE}📝 Preview: {pdf.snippet[:150]}...{Style.RESET_ALL}")
            print(f"   {Fore.MAGENTA}🔍 Source: {pdf.provider}{Style.RESET_ALL}")
            if pdf.timestamp:
                print(f"   🕒 Date: {pdf.timestamp.strftime('%Y-%m-%d')}{Style.RESET_ALL}")
            print()
    
    @staticmethod
    def render_images(results: List[SearchResult]):
        """Render image search results"""
        if not results:
            print(f"{Fore.YELLOW}No images found.{Style.RESET_ALL}")
            return
        
        print(f"\n{Fore.CYAN}{'='*80}{Style.RESET_ALL}")
        print(f"{Fore.GREEN}🖼️ IMAGE SEARCH RESULTS ({len(results)} found){Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")
        
        for idx, img in enumerate(results, 1):
            print(f"{Fore.YELLOW}{idx}. {img.title[:80]}{Style.RESET_ALL}")
            print(f"   {Fore.BLUE}🖼️ URL: {img.url[:80]}{Style.RESET_ALL}")
            print(f"   {Fore.WHITE}📝 {img.snippet}{Style.RESET_ALL}")
            print(f"   {Fore.MAGENTA}🔍 Source: {img.provider}{Style.RESET_ALL}")
            print()
    
    @staticmethod
    def render_web(results: List[SearchResult]):
        """Render web search results"""
        if not results:
            print(f"{Fore.YELLOW}No web results found.{Style.RESET_ALL}")
            return
        
        print(f"\n{Fore.CYAN}{'='*80}{Style.RESET_ALL}")
        print(f"{Fore.GREEN}🌐 WEB SEARCH RESULTS ({len(results)} found){Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")
        
        for idx, page in enumerate(results, 1):
            print(f"{Fore.YELLOW}{idx}. {page.title[:100]}{Style.RESET_ALL}")
            print(f"   {Fore.BLUE}🔗 URL: {page.url[:80]}{Style.RESET_ALL}")
            print(f"   {Fore.WHITE}📝 {page.snippet[:200]}...{Style.RESET_ALL}")
            print(f"   {Fore.MAGENTA}🔍 Source: {page.provider}{Style.RESET_ALL}")
            if page.timestamp:
                print(f"   🕒 Last updated: {page.timestamp.strftime('%Y-%m-%d')}{Style.RESET_ALL}")
            print()
    
    @staticmethod
    def render_jobs(results: List[JobResult]):
        """Render job search results"""
        if not results:
            print(f"{Fore.YELLOW}No job listings found.{Style.RESET_ALL}")
            return
        
        recent_jobs = [j for j in results if j.timestamp and (datetime.now() - j.timestamp).days <= 7]
        older_jobs = [j for j in results if j not in recent_jobs]
        
        print(f"\n{Fore.CYAN}{'='*80}{Style.RESET_ALL}")
        print(f"{Fore.GREEN}💼 JOB SEARCH RESULTS ({len(results)} positions found){Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}")
        
        if recent_jobs:
            print(f"\n{Fore.GREEN}🔥 RECENT POSTINGS (Last 7 days):{Style.RESET_ALL}\n")
            for idx, job in enumerate(recent_jobs, 1):
                SearchRenderer._render_single_job(idx, job)
        
        if older_jobs:
            print(f"\n{Fore.YELLOW}📌 OTHER LISTINGS:{Style.RESET_ALL}\n")
            for idx, job in enumerate(older_jobs, len(recent_jobs) + 1):
                SearchRenderer._render_single_job(idx, job)
    
    @staticmethod
    def _render_single_job(idx: int, job: JobResult):
        """Render a single job listing"""
        print(f"{Fore.YELLOW}{idx}. {job.title[:120]}{Style.RESET_ALL}")
        print(f"   {Fore.CYAN}🏢 Company: {job.company}{Style.RESET_ALL}")
        print(f"   {Fore.BLUE}📍 Location: {job.location}{Style.RESET_ALL}")
        print(f"   {Fore.MAGENTA}💼 Type: {job.job_type}{Style.RESET_ALL}")
        if job.salary:
            print(f"   {Fore.GREEN}💰 Salary: {job.salary}{Style.RESET_ALL}")
        if job.posted_date:
            print(f"   📅 Posted: {job.posted_date}{Style.RESET_ALL}")
        print(f"   {Fore.BLUE}🔗 Apply: {job.url[:80]}{Style.RESET_ALL}")
        print(f"   {Fore.WHITE}📝 {job.snippet[:150]}...{Style.RESET_ALL}")
        print(f"   {Fore.MAGENTA}🔍 Source: {job.provider}{Style.RESET_ALL}")
        print()


class SearchManager:
    """Main search manager with provider selection"""
    
    def __init__(self):
        self.engine = RobustSearchEngine()
        self.renderer = SearchRenderer()
    
    def run(self):
        """Main interactive menu"""
        while True:
            self._show_menu()
            choice = input(f"\n{Fore.CYAN}Enter your choice (1-7): {Style.RESET_ALL}").strip()
            
            if choice == '7':
                print(f"\n{Fore.GREEN}Thank you for using Robust Search Engine! Goodbye!{Style.RESET_ALL}")
                break
            
            if choice == '1':
                self._pdf_search()
            elif choice == '2':
                self._image_search()
            elif choice == '3':
                self._web_search()
            elif choice == '4':
                self._job_search()
            elif choice == '5':
                self._multi_search()
            elif choice == '6':
                self._test_providers()
            else:
                print(f"{Fore.RED}Invalid choice. Please try again.{Style.RESET_ALL}")
    
    def _show_menu(self):
        """Display main menu"""
        print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.GREEN}🔍 ROBUST SEARCH ENGINE (Multi-Provider){Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}1.{Style.RESET_ALL} 📄 Search PDFs")
        print(f"{Fore.YELLOW}2.{Style.RESET_ALL} 🖼️ Search Images")
        print(f"{Fore.YELLOW}3.{Style.RESET_ALL} 🌐 Search Web Pages")
        print(f"{Fore.YELLOW}4.{Style.RESET_ALL} 💼 Search Jobs")
        print(f"{Fore.YELLOW}5.{Style.RESET_ALL} 🔄 Multi-Search (All types)")
        print(f"{Fore.YELLOW}6.{Style.RESET_ALL} 🧪 Test Available Providers")
        print(f"{Fore.YELLOW}7.{Style.RESET_ALL} 🚪 Exit")
    
    def _pdf_search(self):
        keyword = input(f"{Fore.CYAN}Enter PDF search keyword: {Style.RESET_ALL}").strip()
        if not keyword:
            print(f"{Fore.RED}No keyword entered.{Style.RESET_ALL}")
            return
        
        use_parallel = input(f"{Fore.CYAN}Use parallel search (faster, more results)? (y/n): {Style.RESET_ALL}").strip().lower() == 'y'
        limit = self._get_limit()
        
        print(f"\n{Fore.GREEN}Searching for PDFs...{Style.RESET_ALL}")
        results = self.engine.search_pdfs(keyword, limit, use_parallel)
        self.renderer.render_pdfs(results)
    
    def _image_search(self):
        keyword = input(f"{Fore.CYAN}Enter image search keyword: {Style.RESET_ALL}").strip()
        if not keyword:
            print(f"{Fore.RED}No keyword entered.{Style.RESET_ALL}")
            return
        
        use_parallel = input(f"{Fore.CYAN}Use parallel search? (y/n): {Style.RESET_ALL}").strip().lower() == 'y'
        limit = self._get_limit()
        
        print(f"\n{Fore.GREEN}Searching for images...{Style.RESET_ALL}")
        results = self.engine.search_images(keyword, limit, use_parallel)
        self.renderer.render_images(results)
    
    def _web_search(self):
        keyword = input(f"{Fore.CYAN}Enter web search keyword: {Style.RESET_ALL}").strip()
        if not keyword:
            print(f"{Fore.RED}No keyword entered.{Style.RESET_ALL}")
            return
        
        use_parallel = input(f"{Fore.CYAN}Use parallel search? (y/n): {Style.RESET_ALL}").strip().lower() == 'y'
        limit = self._get_limit()
        
        print(f"\n{Fore.GREEN}Searching the web...{Style.RESET_ALL}")
        results = self.engine.search_web(keyword, limit, use_parallel)
        self.renderer.render_web(results)
    
    def _job_search(self):
        print(f"\n{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
        print(f"{Fore.GREEN}💼 JOB SEARCH{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
        
        job_title = input(f"{Fore.CYAN}Enter job title (e.g., 'Software Developer', 'Data Scientist'): {Style.RESET_ALL}").strip()
        if not job_title:
            print(f"{Fore.RED}No job title entered.{Style.RESET_ALL}")
            return
        
        location = input(f"{Fore.CYAN}Enter location (optional): {Style.RESET_ALL}").strip()
        
        print(f"\n{Fore.GREEN}Searching for {job_title} jobs...{Style.RESET_ALL}")
        results = self.engine.search_jobs(job_title, location, limit=30)
        
        if not results:
            print(f"{Fore.YELLOW}No jobs found. Try different keywords.{Style.RESET_ALL}")
            return
        
        self._apply_job_filters(results)
    
    def _apply_job_filters(self, results: List[JobResult]):
        """Interactive job filtering"""
        while True:
            print(f"\n{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
            print(f"{Fore.GREEN}🔧 FILTERS & SORTING{Style.RESET_ALL}")
            print(f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}1.{Style.RESET_ALL} Show all ({len(results)} jobs)")
            print(f"{Fore.YELLOW}2.{Style.RESET_ALL} Filter by days (e.g., last 7 days)")
            print(f"{Fore.YELLOW}3.{Style.RESET_ALL} Filter by job type")
            print(f"{Fore.YELLOW}4.{Style.RESET_ALL} Filter by location")
            print(f"{Fore.YELLOW}5.{Style.RESET_ALL} Sort by newest first")
            print(f"{Fore.YELLOW}6.{Style.RESET_ALL} Sort by oldest first")
            print(f"{Fore.YELLOW}7.{Style.RESET_ALL} Back to main menu")
            
            choice = input(f"\n{Fore.CYAN}Your choice: {Style.RESET_ALL}").strip()
            
            filtered = results.copy()
            
            if choice == '1':
                self.renderer.render_jobs(filtered)
            elif choice == '2':
                days = int(input(f"{Fore.CYAN}Filter jobs posted in last N days: {Style.RESET_ALL}").strip())
                cutoff = datetime.now() - timedelta(days=days)
                filtered = [j for j in results if j.timestamp and j.timestamp >= cutoff]
                self.renderer.render_jobs(filtered)
            elif choice == '3':
                job_type = input(f"{Fore.CYAN}Enter job type (Remote/Full-time/Part-time): {Style.RESET_ALL}").strip()
                filtered = [j for j in results if job_type.lower() in j.job_type.lower()]
                self.renderer.render_jobs(filtered)
            elif choice == '4':
                location = input(f"{Fore.CYAN}Enter location: {Style.RESET_ALL}").strip()
                filtered = [j for j in results if location.lower() in j.location.lower()]
                self.renderer.render_jobs(filtered)
            elif choice == '5':
                filtered.sort(key=lambda x: x.timestamp if x.timestamp else datetime.min, reverse=True)
                self.renderer.render_jobs(filtered)
            elif choice == '6':
                filtered.sort(key=lambda x: x.timestamp if x.timestamp else datetime.min)
                self.renderer.render_jobs(filtered)
            elif choice == '7':
                break
    
    def _multi_search(self):
        keyword = input(f"{Fore.CYAN}Enter search keyword: {Style.RESET_ALL}").strip()
        if not keyword:
            print(f"{Fore.RED}No keyword entered.{Style.RESET_ALL}")
            return
        
        use_parallel = input(f"{Fore.CYAN}Use parallel search? (y/n): {Style.RESET_ALL}").strip().lower() == 'y'
        limit = self._get_limit()
        
        print(f"\n{Fore.GREEN}Performing comprehensive search for '{keyword}'...{Style.RESET_ALL}\n")
        
        pdfs = self.engine.search_pdfs(keyword, limit, use_parallel)
        images = self.engine.search_images(keyword, limit, use_parallel)
        web = self.engine.search_web(keyword, limit, use_parallel)
        jobs = self.engine.search_jobs(keyword, "", limit)
        
        self.renderer.render_pdfs(pdfs)
        self.renderer.render_images(images)
        self.renderer.render_web(web)
        self.renderer.render_jobs(jobs)
    
    def _test_providers(self):
        """Test which search providers are working"""
        print(f"\n{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
        print(f"{Fore.GREEN}🧪 Testing Search Providers{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}\n")
        
        test_query = "Python programming"
        
        for provider in SearchProvider:
            print(f"{Fore.YELLOW}Testing {provider.value}...{Style.RESET_ALL}")
            ms = MultiProviderSearch([provider])
            results = ms.search_with_fallback(test_query, 3, "web")
            
            if results:
                print(f"{Fore.GREEN}✓ {provider.value} is WORKING ({len(results)} results){Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}✗ {provider.value} is NOT AVAILABLE{Style.RESET_ALL}")
            print()
    
    def _get_limit(self) -> int:
        try:
            limit = int(input(f"{Fore.CYAN}Number of results (default 10): {Style.RESET_ALL}").strip() or "10")
            return min(limit, 50)
        except ValueError:
            return 10


if __name__ == "__main__":
    try:
        manager = SearchManager()
        manager.run()
    except KeyboardInterrupt:
        print(f"\n\n{Fore.YELLOW}Search interrupted. Goodbye!{Style.RESET_ALL}")
    except Exception as e:
        print(f"\n{Fore.RED}An error occurred: {e}{Style.RESET_ALL}")