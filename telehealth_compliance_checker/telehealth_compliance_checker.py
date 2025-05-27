import streamlit as st
import requests
from bs4 import BeautifulSoup
import urllib.parse
import re
import logging
from collections import defaultdict
import time
import json
import os
import uuid
import threading
from datetime import datetime

# Set page config
st.set_page_config(
    page_title="Telehealth Compliance Checker",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Define compliance rules
class ComplianceRules:
    """Class to manage compliance rules for telehealth websites."""
    
    @staticmethod
    def get_default_rules():
        """Return default compliance rules with enhancements."""
        return {
            "branded_medications": {
                "category": "fda",
                "severity": "high",
                "patterns": [
                    r"\bOzempic\b",
                    r"\bWegovy\b",
                    r"\bMounjaro\b",
                    r"\bZepbound\b",
                    r"\bSaxenda\b",
                    r"\bVictoza\b",
                    r"\bRybelsus\b",
                    r"\bTrulicity\b"
                ],
                "context_exceptions": [
                    r"not\s+(?:a\s+substitute|the\s+same\s+as)\s+\b(?:Ozempic|Wegovy|Mounjaro|Zepbound|Saxenda|Victoza|Rybelsus|Trulicity)\b",
                    r"(?:unlike|different\s+from)\s+\b(?:Ozempic|Wegovy|Mounjaro|Zepbound|Saxenda|Victoza|Rybelsus|Trulicity)\b"
                ],
                "page_type_rules": {
                    "blog": "allow",  # Allow branded medication mentions in blog posts
                    "product": "check_context",  # Check context in product pages
                    "other": "check_context"  # Default to checking context
                }
            },
            "miracle_claims": {
                "category": "ftc",
                "severity": "high",
                "patterns": [
                    r"\bmiraculous\b",
                    r"\bbreakthrough\b",
                    r"\bmagic\b",
                    r"\binstant\b",
                    r"\bimmediate\b",
                    r"\bovernight\b",
                    r"\bcure\b",
                    r"\bguaranteed\b",
                    r"\b100%\s+effective\b",
                    r"\bno\s+side\s+effects\b",
                    r"\brisk[-\s]free\b"
                ]
            },
            "weight_loss_claims": {
                "category": "ftc",
                "severity": "high",
                "patterns": [
                    r"lose\s+\d+\s+(?:pounds|lbs)",
                    r"lose\s+weight\s+without\s+(?:diet|exercise)",
                    r"effortless\s+weight\s+loss",
                    r"melt\s+away\s+fat",
                    r"burn\s+fat\s+while\s+you\s+sleep"
                ],
                "context_exceptions": [
                    # Allow guarantee terms with specific weight loss amounts and timeframes
                    r"refund\s+(?:your\s+)?money\s+if\s+\d+\s+(?:pounds|lbs|kg)\s+(?:is|are)\s+not\s+lost\s+in\s+\d+\s+(?:days|weeks|months)"
                ]
            },
            "prohibited_terms": {
                "category": "fda",
                "severity": "high",
                "patterns": [
                    r"\bproven\b",
                    r"\befficacy\b",
                    r"\bsafe\b",
                    r"\bsemaglutide\b",
                    r"\btirzepatide\b",
                    r"\bsame\s+ingredients\b"
                ],
                "page_type_rules": {
                    "blog": "check_context",
                    "product": "flag",  # Always flag on product pages
                    "other": "check_context"
                }
            },
            "medical_advice": {
                "category": "fda",
                "severity": "medium",
                "patterns": [
                    r"(?:we|our\s+doctors)\s+(?:recommend|prescribe)",
                    r"(?:we|our\s+doctors)\s+(?:diagnose|treat|cure)",
                    r"self[-\s]diagnose",
                    r"no\s+(?:doctor|physician)\s+visit\s+(?:needed|required|necessary)"
                ]
            },
            "hipaa_issues": {
                "category": "hipaa",
                "severity": "high",
                "patterns": [
                    r"(?:we|our)\s+(?:share|sell)\s+your\s+(?:data|information)",
                    r"third[-\s]parties\s+may\s+access\s+your\s+(?:medical|health)\s+(?:data|information|records)",
                    r"not\s+responsible\s+for\s+(?:data|information)\s+(?:breach|leak|security)"
                ]
            },
            "prescription_issues": {
                "category": "legitscript",
                "severity": "high",
                "patterns": [
                    r"no\s+prescription\s+(?:needed|required|necessary)",
                    r"prescription[-\s]free",
                    r"(?:get|obtain)\s+(?:medication|drugs|medicine)\s+without\s+(?:prescription|doctor)",
                    r"online\s+(?:prescription|doctor)\s+approval\s+guaranteed"
                ]
            },
            "security_issues": {
                "category": "technical",
                "severity": "high",
                "patterns": [
                    r"not\s+secure",
                    r"http://",
                    r"we\s+do\s+not\s+encrypt"
                ]
            }
        }

# Define crawler class
class TelehealthCrawler:
    """Class to crawl telehealth websites and extract content for compliance analysis."""
    
    def __init__(self, start_url, max_pages=20, user_agent="TelehealthComplianceCrawler/1.0"):
        # Normalize the start URL if it doesn't have a protocol
        if not start_url.startswith('http://') and not start_url.startswith('https://'):
            start_url = 'https://' + start_url
            
        self.start_url = start_url
        self.base_domain = self._extract_domain(start_url)
        self.max_pages = max_pages
        self.visited_urls = set()
        self.queue = [start_url]
        self.page_content = {}
        self.forms = {}
        self.images = {}
        self.pdfs = {}
        self.page_types = {}  # Store page types (blog, product, other)
        self.user_agent = user_agent
        
        # Configure logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger('telehealth_crawler')
    
    def _extract_domain(self, url):
        """Extract base domain from URL."""
        parsed_url = urllib.parse.urlparse(url)
        return parsed_url.netloc
    
    def _is_same_domain(self, url):
        """Check if URL belongs to the same domain."""
        parsed_url = urllib.parse.urlparse(url)
        return parsed_url.netloc == self.base_domain
    
    def _normalize_url(self, url, base_url):
        """Normalize URL to absolute form with improved handling."""
        # Remove fragments
        url = url.split('#')[0]
        
        # Handle URLs without protocol
        if not url.startswith('http://') and not url.startswith('https://') and not url.startswith('//'):
            if url.startswith('/'):
                # Relative URL with leading slash
                parsed_base = urllib.parse.urlparse(base_url)
                url = f"{parsed_base.scheme}://{parsed_base.netloc}{url}"
            else:
                # Relative URL without leading slash
                url = urllib.parse.urljoin(base_url, url)
        elif url.startswith('//'):
            # Protocol-relative URL
            parsed_base = urllib.parse.urlparse(base_url)
            url = f"{parsed_base.scheme}:{url}"
        
        # Convert to absolute URL for other cases
        else:
            url = urllib.parse.urljoin(base_url, url)
        
        return url
    
    def _extract_links(self, soup, base_url):
        """Extract all links from a page."""
        links = []
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            absolute_url = self._normalize_url(href, base_url)
            if self._is_same_domain(absolute_url) and absolute_url not in self.visited_urls:
                links.append(absolute_url)
        return links
    
    def _extract_forms(self, soup, url):
        """Extract forms from a page."""
        forms_data = []
        for form in soup.find_all('form'):
            form_data = {
                'action': form.get('action', ''),
                'method': form.get('method', 'get'),
                'inputs': []
            }
            
            for input_tag in form.find_all(['input', 'textarea', 'select']):
                input_data = {
                    'type': input_tag.get('type', 'text'),
                    'name': input_tag.get('name', ''),
                    'id': input_tag.get('id', ''),
                    'placeholder': input_tag.get('placeholder', ''),
                    'required': input_tag.has_attr('required')
                }
                form_data['inputs'].append(input_data)
            
            forms_data.append(form_data)
        
        if forms_data:
            self.forms[url] = forms_data
    
    def _extract_images(self, soup, url):
        """Extract images from a page."""
        images_data = []
        for img in soup.find_all('img'):
            image_data = {
                'src': img.get('src', ''),
                'alt': img.get('alt', ''),
                'title': img.get('title', '')
            }
            images_data.append(image_data)
        
        if images_data:
            self.images[url] = images_data
    
    def _extract_pdfs(self, soup, url):
        """Extract links to PDF files."""
        pdf_links = []
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            if href.lower().endswith('.pdf'):
                absolute_url = self._normalize_url(href, url)
                pdf_links.append({
                    'url': absolute_url,
                    'text': a_tag.get_text(strip=True)
                })
        
        if pdf_links:
            self.pdfs[url] = pdf_links
    
    def _detect_page_type(self, url, soup, text):
        """
        Detect the type of page (blog, product, etc.)
        
        Returns:
            str: Page type ('blog', 'product', 'other')
        """
        # Check URL patterns
        blog_url_patterns = [
            r'/blog/', r'/articles/', r'/news/', r'/insights/',
            r'/resources/', r'/learn/', r'/education/'
        ]
        
        product_url_patterns = [
            r'/product/', r'/shop/', r'/buy/', r'/order/',
            r'/pricing/', r'/plans/', r'/subscription/'
        ]
        
        # Check URL for blog indicators
        for pattern in blog_url_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return 'blog'
        
        # Check URL for product indicators
        for pattern in product_url_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return 'product'
        
        # Check content indicators if URL patterns don't match
        
        # Blog indicators in content
        blog_indicators = [
            # Headers that suggest blog content
            r'<h\d[^>]*>\s*(?:blog|article|post|news)\s*</h\d>',
            # Publication date patterns
            r'published\s+on|posted\s+on|date:',
            # Author bylines
            r'by\s+[a-z\s\.]+\s*(?:\||,|\()\s*[a-z]{3,}\s+\d{1,2},?\s+\d{4}',
            # Common blog metadata
            r'<meta[^>]*(?:article:published_time|article:author|og:article)'
        ]
        
        # Product indicators in content
        product_indicators = [
            # Price indicators
            r'\$\d+(?:\.\d{2})?',
            # Add to cart/buy now buttons
            r'add\s+to\s+cart|buy\s+now|purchase|subscribe|get\s+started',
            # Product description indicators
            r'product\s+details|specifications|ingredients|what\'s\s+included',
            # Shipping information
            r'shipping|delivery|in\s+stock'
        ]
        
        # Check HTML for blog indicators
        blog_score = 0
        html_str = str(soup)
        for pattern in blog_indicators:
            if re.search(pattern, html_str, re.IGNORECASE):
                blog_score += 1
        
        # Check HTML for product indicators
        product_score = 0
        for pattern in product_indicators:
            if re.search(pattern, html_str, re.IGNORECASE):
                product_score += 1
        
        # Determine page type based on scores
        if blog_score > product_score and blog_score >= 2:
            return 'blog'
        elif product_score > blog_score and product_score >= 2:
            return 'product'
        else:
            return 'other'
    
    def _get_page_content(self, url):
        """Get page content with enhanced handling for difficult sites."""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Referer': 'https://www.google.com/',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Cache-Control': 'max-age=0'
            }
            
            # Add special handling for known problematic sites
            if 'hims.com' in url or 'forhims.com' in url:
                # Add additional headers for hims.com
                headers['Cookie'] = 'session=placeholder; visitor=new'
                
                # Use a longer timeout for hims.com
                timeout = 20
            else:
                timeout = 10
            
            response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
            
            # Handle potential cloudflare or other protection
            if response.status_code == 403 or response.status_code == 503:
                self.logger.warning(f"Access denied for {url}, possibly due to protection mechanisms")
                # Could implement more sophisticated handling here
                
            return response
            
        except Exception as e:
            self.logger.error(f"Error fetching {url}: {e}")
            return None
    
    def crawl(self, progress_callback=None):
        """Start crawling the website."""
        self.logger.info(f"Starting crawl from {self.start_url}")
        
        while self.queue and len(self.visited_urls) < self.max_pages:
            current_url = self.queue.pop(0)
            
            if current_url in self.visited_urls:
                continue
            
            self.logger.info(f"Crawling: {current_url}")
            if progress_callback:
                progress_callback(f"Crawling: {current_url}", len(self.visited_urls) / self.max_pages)
            
            try:
                response = self._get_page_content(current_url)
                
                if response and response.status_code == 200:
                    # Parse with BeautifulSoup
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Detect page type
                    page_type = self._detect_page_type(current_url, soup, response.text)
                    self.page_types[current_url] = page_type
                    
                    # Store page content
                    self.page_content[current_url] = {
                        'title': soup.title.string if soup.title else '',
                        'html': response.text,
                        'text': soup.get_text(separator=' ', strip=True),
                        'meta_description': soup.find('meta', attrs={'name': 'description'})['content'] if soup.find('meta', attrs={'name': 'description'}) else '',
                        'headers': [h.get_text(strip=True) for h in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])],
                        'page_type': page_type
                    }
                    
                    # Extract forms, images, and PDFs
                    self._extract_forms(soup, current_url)
                    self._extract_images(soup, current_url)
                    self._extract_pdfs(soup, current_url)
                    
                    # Extract links and add to queue
                    links = self._extract_links(soup, current_url)
                    for link in links:
                        if link not in self.visited_urls and link not in self.queue:
                            self.queue.append(link)
                    
                    # Mark as visited
                    self.visited_urls.add(current_url)
                else:
                    status_code = response.status_code if response else "Connection failed"
                    self.logger.warning(f"Failed to fetch {current_url}: HTTP {status_code}")
                
            except Exception as e:
                self.logger.error(f"Error crawling {current_url}: {e}")
        
        self.logger.info(f"Crawl completed. Visited {len(self.visited_urls)} pages.")
        
        return {
            'pages': self.page_content,
            'forms': self.forms,
            'images': self.images,
            'pdfs': self.pdfs,
            'page_types': self.page_types
        }

# Define analyzer class
class ComplianceAnalyzer:
    """Class to analyze website content for compliance issues."""
    
    def __init__(self, crawler_data):
        self.crawler_data = crawler_data
        self.pages = crawler_data['pages']
        self.forms = crawler_data['forms']
        self.images = crawler_data['images']
        self.pdfs = crawler_data['pdfs']
        self.page_types = crawler_data['page_types']
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger('compliance_analyzer')
        
        # Load compliance rules
        self.rules = ComplianceRules.get_default_rules()
        
        # Initialize findings
        self.findings = defaultdict(list)
        self.scores = {
            'hipaa': 0,
            'fda': 0,
            'legitscript': 0,
            'ftc': 0,
            'technical': 0,
            'total': 0
        }
    
    def analyze_pages(self, progress_callback=None):
        """Analyze all pages for compliance issues."""
        self.logger.info("Starting compliance analysis")
        
        total_pages = len(self.pages)
        for i, (url, page_data) in enumerate(self.pages.items()):
            self.logger.info(f"Analyzing page: {url}")
            if progress_callback:
                progress_callback(f"Analyzing page: {url}", i / total_pages)
            
            # Get page type
            page_type = page_data.get('page_type', 'other')
            
            # Analyze page content
            self._analyze_text_content(url, page_data['text'], page_data['title'], page_type)
            
            # Analyze headers
            self._analyze_headers(url, page_data['headers'], page_type)
            
            # Check for HTTPS
            self._check_https(url)
            
            # Analyze forms if present
            if url in self.forms:
                self._analyze_forms(url, self.forms[url], page_type)
            
            # Analyze images if present
            if url in self.images:
                self._analyze_images(url, self.images[url], page_type)
        
        # Check for privacy policy and terms
        self._check_required_pages()
        
        # Calculate scores
        self._calculate_scores()
        
        return {
            'findings': dict(self.findings),
            'scores': self.scores
        }
    
    def _analyze_text_content(self, url, text, title, page_type):
        """Analyze page text content for compliance issues with context awareness."""
        # Check each rule against the text
        for rule_name, rule in self.rules.items():
            # Check if rule has page type specific handling
            if 'page_type_rules' in rule and page_type in rule['page_type_rules']:
                rule_action = rule['page_type_rules'][page_type]
                
                # Skip checking if rule action is to allow
                if rule_action == 'allow':
                    continue
                    
                # Always flag if rule action is to flag
                elif rule_action == 'flag':
                    # Process all patterns without exceptions
                    for pattern in rule['patterns']:
                        matches = re.finditer(pattern, text, re.IGNORECASE)
                        
                        for match in matches:
                            # Get surrounding context
                            start = max(0, match.start() - 50)
                            end = min(len(text), match.end() + 50)
                            context = text[start:end]
                            
                            # Add finding
                            self.findings[url].append({
                                'type': rule_name,
                                'category': rule['category'],
                                'severity': rule['severity'],
                                'pattern': pattern,
                                'matched_text': match.group(0),
                                'context': context.strip(),
                                'location': 'page_content',
                                'page_type': page_type
                            })
                    
                    # Skip to next rule
                    continue
            
            # Standard pattern checking with exceptions
            for pattern in rule['patterns']:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                
                for match in matches:
                    # Check if match is in an exception context
                    if 'context_exceptions' in rule:
                        exception_found = False
                        for exception in rule['context_exceptions']:
                            # Get surrounding context (100 chars before and after)
                            start = max(0, match.start() - 100)
                            end = min(len(text), match.end() + 100)
                            context = text[start:end]
                            
                            if re.search(exception, context, re.IGNORECASE):
                                exception_found = True
                                break
                        
                        if exception_found:
                            continue
                    
                    # Get surrounding context (50 chars before and after)
                    start = max(0, match.start() - 50)
                    end = min(len(text), match.end() + 50)
                    context = text[start:end]
                    
                    # Add finding
                    self.findings[url].append({
                        'type': rule_name,
                        'category': rule['category'],
                        'severity': rule['severity'],
                        'pattern': pattern,
                        'matched_text': match.group(0),
                        'context': context.strip(),
                        'location': 'page_content',
                        'page_type': page_type
                    })
    
    def _analyze_headers(self, url, headers, page_type):
        """Analyze page headers for compliance issues."""
        for header in headers:
            for rule_name, rule in self.rules.items():
                # Check if rule has page type specific handling
                if 'page_type_rules' in rule and page_type in rule['page_type_rules']:
                    rule_action = rule['page_type_rules'][page_type]
                    
                    # Skip checking if rule action is to allow
                    if rule_action == 'allow':
                        continue
                
                for pattern in rule['patterns']:
                    if re.search(pattern, header, re.IGNORECASE):
                        # Check if match is in an exception context
                        if 'context_exceptions' in rule:
                            exception_found = False
                            for exception in rule['context_exceptions']:
                                if re.search(exception, header, re.IGNORECASE):
                                    exception_found = True
                                    break
                            
                            if exception_found:
                                continue
                        
                        # Add finding
                        self.findings[url].append({
                            'type': rule_name,
                            'category': rule['category'],
                            'severity': rule['severity'],
                            'pattern': pattern,
                            'matched_text': header,
                            'context': header,
                            'location': 'header',
                            'page_type': page_type
                        })
    
    def _check_https(self, url):
        """Check if page uses HTTPS."""
        if url.startswith('http://'):
            self.findings[url].append({
                'type': 'security_issues',
                'category': 'technical',
                'severity': 'high',
                'pattern': 'http://',
                'matched_text': url,
                'context': f"Non-secure URL: {url}",
                'location': 'url'
            })
    
    def _analyze_forms(self, url, forms, page_type):
        """Analyze forms for compliance issues."""
        for form_index, form in enumerate(forms):
            # Check for sensitive input types
            sensitive_inputs = []
            for input_data in form['inputs']:
                input_type = input_data.get('type', '').lower()
                input_name = input_data.get('name', '').lower()
                input_id = input_data.get('id', '').lower()
                input_placeholder = input_data.get('placeholder', '').lower()
                
                # Check for health-related inputs
                health_patterns = [
                    r'health', r'medical', r'symptom', r'condition',
                    r'diagnosis', r'treatment', r'medication', r'prescription',
                    r'weight', r'height', r'bmi', r'blood'
                ]
                
                for pattern in health_patterns:
                    if (re.search(pattern, input_name, re.IGNORECASE) or
                        re.search(pattern, input_id, re.IGNORECASE) or
                        re.search(pattern, input_placeholder, re.IGNORECASE)):
                        sensitive_inputs.append(input_data)
            
            # Check if form has HTTPS action
            if form['action'] and form['action'].startswith('http://'):
                self.findings[url].append({
                    'type': 'security_issues',
                    'category': 'technical',
                    'severity': 'high',
                    'pattern': 'http://',
                    'matched_text': form['action'],
                    'context': f"Form submits to non-secure URL: {form['action']}",
                    'location': f"form_{form_index}_action",
                    'page_type': page_type
                })
            
            # Check if sensitive form doesn't use POST method
            if sensitive_inputs and form['method'].lower() != 'post':
                self.findings[url].append({
                    'type': 'security_issues',
                    'category': 'technical',
                    'severity': 'medium',
                    'pattern': 'form method',
                    'matched_text': form['method'],
                    'context': f"Form with sensitive health information uses {form['method']} method instead of POST",
                    'location': f"form_{form_index}_method",
                    'page_type': page_type
                })
    
    def _analyze_images(self, url, images, page_type):
        """Analyze images for compliance issues."""
        for image_index, image in enumerate(images):
            # Check alt text and title for compliance issues
            for text_field in ['alt', 'title']:
                if not image[text_field]:
                    continue
                
                for rule_name, rule in self.rules.items():
                    # Check if rule has page type specific handling
                    if 'page_type_rules' in rule and page_type in rule['page_type_rules']:
                        rule_action = rule['page_type_rules'][page_type]
                        
                        # Skip checking if rule action is to allow
                        if rule_action == 'allow':
                            continue
                    
                    for pattern in rule['patterns']:
                        if re.search(pattern, image[text_field], re.IGNORECASE):
                            # Check if match is in an exception context
                            if 'context_exceptions' in rule:
                                exception_found = False
                                for exception in rule['context_exceptions']:
                                    if re.search(exception, image[text_field], re.IGNORECASE):
                                        exception_found = True
                                        break
                                
                                if exception_found:
                                    continue
                            
                            self.findings[url].append({
                                'type': rule_name,
                                'category': rule['category'],
                                'severity': rule['severity'],
                                'pattern': pattern,
                                'matched_text': image[text_field],
                                'context': f"Image {text_field}: {image[text_field]}",
                                'location': f"image_{text_field}",
                                'page_type': page_type
                            })
    
    def _check_required_pages(self):
        """Check for required pages like privacy policy and terms."""
        privacy_found = False
        terms_found = False
        
        privacy_patterns = [r'privacy', r'privacy\s+policy', r'privacy\s+notice']
        terms_patterns = [r'terms', r'terms\s+of\s+(?:use|service)', r'conditions']
        
        for url in self.pages.keys():
            # Check URL for privacy policy
            for pattern in privacy_patterns:
                if re.search(pattern, url, re.IGNORECASE):
                    privacy_found = True
            
            # Check URL for terms
            for pattern in terms_patterns:
                if re.search(pattern, url, re.IGNORECASE):
                    terms_found = True
        
        # Check page content if not found in URLs
        if not privacy_found or not terms_found:
            for url, page_data in self.pages.items():
                text = page_data['text'].lower()
                
                # Check for privacy policy links
                if not privacy_found:
                    for pattern in privacy_patterns:
                        if re.search(pattern, text, re.IGNORECASE):
                            privacy_found = True
                
                # Check for terms links
                if not terms_found:
                    for pattern in terms_patterns:
                        if re.search(pattern, text, re.IGNORECASE):
                            terms_found = True
        
        # Add findings if required pages are missing
        if not privacy_found:
            self.findings['site_wide'].append({
                'type': 'missing_privacy_policy',
                'category': 'hipaa',
                'severity': 'high',
                'pattern': 'privacy policy',
                'matched_text': 'N/A',
                'context': 'No privacy policy found on the website',
                'location': 'site_wide'
            })
        
        if not terms_found:
            self.findings['site_wide'].append({
                'type': 'missing_terms',
                'category': 'legal',
                'severity': 'medium',
                'pattern': 'terms of service',
                'matched_text': 'N/A',
                'context': 'No terms of service found on the website',
                'location': 'site_wide'
            })
    
    def _calculate_scores(self):
        """Calculate compliance scores based on findings."""
        # Initialize category counts
        category_counts = {
            'hipaa': {'high': 0, 'medium': 0, 'low': 0},
            'fda': {'high': 0, 'medium': 0, 'low': 0},
            'legitscript': {'high': 0, 'medium': 0, 'low': 0},
            'ftc': {'high': 0, 'medium': 0, 'low': 0},
            'technical': {'high': 0, 'medium': 0, 'low': 0}
        }
        
        # Count findings by category and severity
        for url, url_findings in self.findings.items():
            for finding in url_findings:
                category = finding['category']
                severity = finding['severity']
                
                if category in category_counts and severity in category_counts[category]:
                    category_counts[category][severity] += 1
        
        # Calculate scores
        # HIPAA (25 points)
        hipaa_deductions = (
            category_counts['hipaa']['high'] * 5 +
            category_counts['hipaa']['medium'] * 2 +
            category_counts['hipaa']['low'] * 0.5
        )
        self.scores['hipaa'] = max(0, 25 - min(hipaa_deductions, 25))
        
        # FDA (25 points)
        fda_deductions = (
            category_counts['fda']['high'] * 5 +
            category_counts['fda']['medium'] * 2 +
            category_counts['fda']['low'] * 0.5
        )
        self.scores['fda'] = max(0, 25 - min(fda_deductions, 25))
        
        # LegitScript (20 points)
        legitscript_deductions = (
            category_counts['legitscript']['high'] * 4 +
            category_counts['legitscript']['medium'] * 1.5 +
            category_counts['legitscript']['low'] * 0.5
        )
        self.scores['legitscript'] = max(0, 20 - min(legitscript_deductions, 20))
        
        # FTC (15 points)
        ftc_deductions = (
            category_counts['ftc']['high'] * 3 +
            category_counts['ftc']['medium'] * 1.5 +
            category_counts['ftc']['low'] * 0.5
        )
        self.scores['ftc'] = max(0, 15 - min(ftc_deductions, 15))
        
        # Technical (15 points)
        technical_deductions = (
            category_counts['technical']['high'] * 3 +
            category_counts['technical']['medium'] * 1.5 +
            category_counts['technical']['low'] * 0.5
        )
        self.scores['technical'] = max(0, 15 - min(technical_deductions, 15))
        
        # Calculate total score (out of 100)
        self.scores['total'] = sum([
            self.scores['hipaa'],
            self.scores['fda'],
            self.scores['legitscript'],
            self.scores['ftc'],
            self.scores['technical']
        ])

# Define recommendations generator class
class RecommendationsGenerator:
    """Class to generate recommendations based on compliance findings."""
    
    def __init__(self, analysis_results):
        self.findings = analysis_results['findings']
        self.scores = analysis_results['scores']
        self.recommendations = {
            'high_priority': [],
            'medium_priority': [],
            'low_priority': []
        }
        self.recommendation_templates = self._load_recommendation_templates()
    
    def _load_recommendation_templates(self):
        """Load recommendation templates."""
        return {
            "branded_medications": {
                "high": "Remove all references to branded medications like {matched_text} unless specifically authorized by the manufacturer. Replace with generic terms like 'GLP-1 medication' or 'semaglutide'.",
                "medium": "Ensure all references to {matched_text} include proper context and disclaimers about the relationship between your service and the branded medication.",
                "low": "Consider adding additional context around mentions of {matched_text} to clarify your service's relationship to this medication."
            },
            "miracle_claims": {
                "high": "Remove exaggerated claims using terms like '{matched_text}' as these violate FTC guidelines for truthful advertising.",
                "medium": "Modify language around '{matched_text}' to avoid implying guaranteed or exceptional results.",
                "low": "Consider toning down language around '{matched_text}' to ensure claims are substantiated and realistic."
            },
            "weight_loss_claims": {
                "high": "Remove specific weight loss claims like '{matched_text}' as these violate FTC guidelines without proper substantiation.",
                "medium": "Modify weight loss claims around '{matched_text}' to include proper disclaimers about typical results and necessary lifestyle changes.",
                "low": "Consider adding additional context to weight loss statements involving '{matched_text}' to ensure they're balanced and realistic."
            },
            "prohibited_terms": {
                "high": "Remove prohibited terms like '{matched_text}' as these may violate FDA regulations regarding prescription drug marketing.",
                "medium": "Modify language around '{matched_text}' to avoid making claims that require FDA approval.",
                "low": "Consider rephrasing content containing '{matched_text}' to ensure compliance with FDA guidelines."
            },
            "medical_advice": {
                "high": "Remove language that suggests direct medical advice like '{matched_text}' without proper evaluation.",
                "medium": "Modify statements like '{matched_text}' to clarify that recommendations are personalized based on individual consultation.",
                "low": "Consider adding disclaimers near '{matched_text}' to clarify the role of medical professionals in the treatment process."
            },
            "hipaa_issues": {
                "high": "Revise statements about data handling like '{matched_text}' to ensure HIPAA compliance regarding patient information.",
                "medium": "Add more specific privacy protections and disclosures around '{matched_text}' to strengthen HIPAA compliance.",
                "low": "Consider enhancing privacy language around '{matched_text}' with more specific HIPAA-compliant terms."
            },
            "prescription_issues": {
                "high": "Remove language suggesting prescriptions without proper evaluation like '{matched_text}' as this violates prescribing regulations.",
                "medium": "Clarify the prescription process around '{matched_text}' to ensure it reflects a legitimate doctor-patient relationship.",
                "low": "Consider adding more detail about the prescription process near '{matched_text}' to emphasize medical oversight."
            },
            "security_issues": {
                "high": "Implement secure protocols to address '{matched_text}' to protect patient data in compliance with HIPAA requirements.",
                "medium": "Enhance security measures around '{matched_text}' to better protect sensitive health information.",
                "low": "Consider upgrading security features related to '{matched_text}' for improved data protection."
            },
            "accessibility_issues": {
                "high": "Add missing accessibility features like alt text for '{matched_text}' to comply with ADA requirements.",
                "medium": "Improve accessibility around '{matched_text}' to better serve all users and comply with guidelines.",
                "low": "Consider enhancing accessibility features related to '{matched_text}' for improved user experience."
            },
            "missing_privacy_policy": {
                "high": "Create and prominently link to a comprehensive HIPAA-compliant privacy policy that details how patient information is collected, used, stored, and protected.",
                "medium": "Ensure your privacy policy is easily accessible from all pages and covers all required HIPAA elements.",
                "low": "Review and enhance your privacy policy to ensure it meets all HIPAA requirements."
            },
            "missing_terms": {
                "high": "Create and prominently link to terms of service that clearly outline the relationship between your service and users, including medical disclaimers.",
                "medium": "Ensure your terms of service are easily accessible and cover all necessary legal protections.",
                "low": "Review and enhance your terms of service to ensure comprehensive coverage of telehealth-specific issues."
            }
        }
    
    def generate_recommendations(self, progress_callback=None):
        """Generate recommendations based on findings."""
        # Process findings and generate recommendations
        total_findings = sum(len(findings) for findings in self.findings.values())
        processed_findings = 0
        
        for url, url_findings in self.findings.items():
            for finding in url_findings:
                finding_type = finding['type']
                severity = finding['severity']
                matched_text = finding['matched_text']
                page_type = finding.get('page_type', 'other')
                
                if progress_callback:
                    processed_findings += 1
                    progress_callback(f"Generating recommendations...", processed_findings / total_findings)
                
                # Get recommendation template
                if finding_type in self.recommendation_templates and severity in self.recommendation_templates[finding_type]:
                    template = self.recommendation_templates[finding_type][severity]
                    recommendation = template.format(matched_text=matched_text)
                    
                    # Add location information
                    location_info = f"URL: {url}" if url != 'site_wide' else "Site-wide issue"
                    if page_type != 'other':
                        location_info += f" (Page type: {page_type})"
                    
                    # Add to appropriate priority list
                    if severity == 'high':
                        self.recommendations['high_priority'].append({
                            'recommendation': recommendation,
                            'location': location_info,
                            'context': finding['context'],
                            'category': finding['category']
                        })
                    elif severity == 'medium':
                        self.recommendations['medium_priority'].append({
                            'recommendation': recommendation,
                            'location': location_info,
                            'context': finding['context'],
                            'category': finding['category']
                        })
                    else:
                        self.recommendations['low_priority'].append({
                            'recommendation': recommendation,
                            'location': location_info,
                            'context': finding['context'],
                            'category': finding['category']
                        })
        
        # Add general recommendations based on scores
        self._add_general_recommendations()
        
        return {
            'recommendations': self.recommendations,
            'scores': self.scores
        }
    
    def _add_general_recommendations(self):
        """Add general recommendations based on scores."""
        # HIPAA recommendations
        if self.scores['hipaa'] < 15:
            self.recommendations['high_priority'].append({
                'recommendation': "Conduct a comprehensive HIPAA compliance review with a focus on privacy policies, data security, and patient rights disclosures.",
                'location': "Site-wide issue",
                'context': "Low HIPAA compliance score",
                'category': "hipaa"
            })
        elif self.scores['hipaa'] < 20:
            self.recommendations['medium_priority'].append({
                'recommendation': "Enhance HIPAA compliance by reviewing and updating privacy policies and security measures.",
                'location': "Site-wide issue",
                'context': "Moderate HIPAA compliance score",
                'category': "hipaa"
            })
        
        # FDA recommendations
        if self.scores['fda'] < 15:
            self.recommendations['high_priority'].append({
                'recommendation': "Review all medication-related content to ensure compliance with FDA regulations regarding prescription drug promotion and claims.",
                'location': "Site-wide issue",
                'context': "Low FDA compliance score",
                'category': "fda"
            })
        elif self.scores['fda'] < 20:
            self.recommendations['medium_priority'].append({
                'recommendation': "Enhance FDA compliance by reviewing medication references and ensuring proper context for all drug mentions.",
                'location': "Site-wide issue",
                'context': "Moderate FDA compliance score",
                'category': "fda"
            })
        
        # LegitScript recommendations
        if self.scores['legitscript'] < 12:
            self.recommendations['high_priority'].append({
                'recommendation': "Review prescription processes and pharmacy relationships to ensure compliance with LegitScript requirements for telehealth services.",
                'location': "Site-wide issue",
                'context': "Low LegitScript compliance score",
                'category': "legitscript"
            })
        elif self.scores['legitscript'] < 16:
            self.recommendations['medium_priority'].append({
                'recommendation': "Enhance LegitScript compliance by reviewing prescription processes and ensuring all medication-related content meets telehealth standards.",
                'location': "Site-wide issue",
                'context': "Moderate LegitScript compliance score",
                'category': "legitscript"
            })
        
        # FTC recommendations
        if self.scores['ftc'] < 9:
            self.recommendations['high_priority'].append({
                'recommendation': "Review all marketing claims to ensure compliance with FTC truth-in-advertising requirements, particularly regarding weight loss claims.",
                'location': "Site-wide issue",
                'context': "Low FTC compliance score",
                'category': "ftc"
            })
        elif self.scores['ftc'] < 12:
            self.recommendations['medium_priority'].append({
                'recommendation': "Enhance FTC compliance by reviewing marketing claims and ensuring all testimonials and results are properly substantiated.",
                'location': "Site-wide issue",
                'context': "Moderate FTC compliance score",
                'category': "ftc"
            })
        
        # Technical recommendations
        if self.scores['technical'] < 9:
            self.recommendations['high_priority'].append({
                'recommendation': "Address critical technical issues, particularly focusing on secure connections (HTTPS) and proper form handling for sensitive information.",
                'location': "Site-wide issue",
                'context': "Low technical compliance score",
                'category': "technical"
            })
        elif self.scores['technical'] < 12:
            self.recommendations['medium_priority'].append({
                'recommendation': "Enhance technical compliance by reviewing security measures and ensuring all data transmission is properly secured.",
                'location': "Site-wide issue",
                'context': "Moderate technical compliance score",
                'category': "technical"
            })

# Define the Streamlit app
def main():
    st.title("Telehealth Compliance Checker")
    st.markdown("Analyze telehealth websites for HIPAA, FDA, LegitScript, and FTC compliance issues.")
    
    # Sidebar
    st.sidebar.header("Settings")
    max_pages = st.sidebar.slider("Maximum pages to crawl", 5, 50, 20)
    
    # Input for URL
    url = st.text_input("Enter telehealth website URL to analyze:", placeholder="e.g., example.com or https://example.com")
    
    if st.button("Analyze Website"):
        if url:
            # Normalize URL if needed
            if not url.startswith('http://') and not url.startswith('https://'):
                url = 'https://' + url
            
            # Create progress bars
            crawl_progress = st.progress(0)
            analysis_progress = st.progress(0)
            recommendation_progress = st.progress(0)
            
            # Status messages
            status = st.empty()
            
            # Crawl website
            status.text("Crawling website...")
            crawler = TelehealthCrawler(url, max_pages=max_pages)
            
            def crawl_callback(message, progress):
                status.text(message)
                crawl_progress.progress(progress)
            
            crawler_data = crawler.crawl(progress_callback=crawl_callback)
            
            # Analyze content
            status.text("Analyzing content for compliance issues...")
            analyzer = ComplianceAnalyzer(crawler_data)
            
            def analysis_callback(message, progress):
                status.text(message)
                analysis_progress.progress(progress)
            
            analysis_results = analyzer.analyze_pages(progress_callback=analysis_callback)
            
            # Generate recommendations
            status.text("Generating recommendations...")
            recommender = RecommendationsGenerator(analysis_results)
            
            def recommendation_callback(message, progress):
                status.text(message)
                recommendation_progress.progress(progress)
            
            recommendations = recommender.generate_recommendations(progress_callback=recommendation_callback)
            
            # Display results
            status.text("Analysis complete!")
            
            # Display scores
            st.header("Compliance Scores")
            col1, col2, col3, col4, col5 = st.columns(5)
            
            with col1:
                st.metric("HIPAA", f"{recommendations['scores']['hipaa']:.1f}/25")
            with col2:
                st.metric("FDA", f"{recommendations['scores']['fda']:.1f}/25")
            with col3:
                st.metric("LegitScript", f"{recommendations['scores']['legitscript']:.1f}/20")
            with col4:
                st.metric("FTC", f"{recommendations['scores']['ftc']:.1f}/15")
            with col5:
                st.metric("Technical", f"{recommendations['scores']['technical']:.1f}/15")
            
            st.metric("Overall Compliance Score", f"{recommendations['scores']['total']:.1f}/100")
            
            # Display recommendations
            st.header("Recommendations")
            
            tab1, tab2, tab3 = st.tabs(["High Priority", "Medium Priority", "Low Priority"])
            
            with tab1:
                if recommendations['recommendations']['high_priority']:
                    for i, rec in enumerate(recommendations['recommendations']['high_priority']):
                        with st.expander(f"{i+1}. {rec['recommendation'][:100]}..."):
                            st.markdown(f"**Recommendation:** {rec['recommendation']}")
                            st.markdown(f"**Location:** {rec['location']}")
                            st.markdown(f"**Category:** {rec['category'].upper()}")
                            st.markdown(f"**Context:** \"{rec['context']}\"")
                else:
                    st.info("No high priority issues found.")
            
            with tab2:
                if recommendations['recommendations']['medium_priority']:
                    for i, rec in enumerate(recommendations['recommendations']['medium_priority']):
                        with st.expander(f"{i+1}. {rec['recommendation'][:100]}..."):
                            st.markdown(f"**Recommendation:** {rec['recommendation']}")
                            st.markdown(f"**Location:** {rec['location']}")
                            st.markdown(f"**Category:** {rec['category'].upper()}")
                            st.markdown(f"**Context:** \"{rec['context']}\"")
                else:
                    st.info("No medium priority issues found.")
            
            with tab3:
                if recommendations['recommendations']['low_priority']:
                    for i, rec in enumerate(recommendations['recommendations']['low_priority']):
                        with st.expander(f"{i+1}. {rec['recommendation'][:100]}..."):
                            st.markdown(f"**Recommendation:** {rec['recommendation']}")
                            st.markdown(f"**Location:** {rec['location']}")
                            st.markdown(f"**Category:** {rec['category'].upper()}")
                            st.markdown(f"**Context:** \"{rec['context']}\"")
                else:
                    st.info("No low priority issues found.")
            
            # Display crawled pages
            st.header("Crawled Pages")
            with st.expander("View crawled pages"):
                for i, url in enumerate(crawler_data['pages'].keys()):
                    page_type = crawler_data['pages'][url].get('page_type', 'other')
                    st.markdown(f"{i+1}. [{url}]({url}) - Page type: {page_type}")
            
            # Display reference materials
            display_reference_materials()
            
        else:
            st.error("Please enter a valid URL.")

def display_reference_materials():
    """Display reference materials for GLP-1 compliance."""
    st.header("GLP-1 Compliance Reference Materials")
    
    st.subheader("Prohibited Terms for GLP-1 Marketing")
    st.markdown("""
    The following terms should be avoided when marketing GLP-1 medications:
    - **Proven**: Implies definitive efficacy without proper context
    - **Efficacy**: Makes medical claims about the effectiveness
    - **Safe**: Makes safety claims that require FDA approval
    - **Semaglutide**: Branded ingredient requiring prescription
    - **Tirzepatide**: Branded ingredient requiring prescription
    - **Same ingredients**: Implies equivalence to FDA-approved medications
    """)
    
    st.subheader("Manufacturer Guidelines")
    
    st.markdown("""
    #### Novo Nordisk (Ozempic, Wegovy, Saxenda)
    - Avoid direct comparisons to branded medications
    - Do not imply that compounded products are the same as FDA-approved medications
    - Clearly distinguish between informational content and marketing claims
    
    #### Lilly (Mounjaro, Zepbound)
    - Avoid claims of equivalence to branded medications
    - Do not use branded terms in product marketing
    - Maintain clear separation between educational content and product promotion
    """)
    
    st.subheader("Guarantee Terms Guidelines")
    st.markdown("""
    Money-back guarantees are permitted when:
    - They specify a concrete amount of weight loss
    - They specify a concrete timeframe
    - They do not make unrealistic claims
    
    Example of acceptable guarantee: "We'll refund your money if you don't lose at least 10 pounds in 3 months."
    """)

if __name__ == "__main__":
    main()
