import time
import logging
import requests
from functools import wraps
from collections import deque
from thefuzz import fuzz
from ratelimit import limits, sleep_and_retry
from title_normalizer import clean_title_for_search, normalize_text


class APIHealthError(Exception):
    pass


class APIErrorTracker:
    def __init__(self, max_error_rate=0.8, window_seconds=300, min_attempts=10, max_consecutive_failures=5):
        self.max_error_rate = max_error_rate
        self.window_seconds = window_seconds
        self.min_attempts = min_attempts
        self.max_consecutive_failures = max_consecutive_failures
        self.history = deque()
        self.consecutive_failures = 0
    
    def _clean_old_entries(self):
        current_time = time.time()
        cutoff_time = current_time - self.window_seconds
        
        while self.history and self.history[0][0] < cutoff_time:
            self.history.popleft()
    
    def record_attempt(self, success):
        current_time = time.time()
        
        if success:
            self.consecutive_failures = 0
        else:
            self.consecutive_failures += 1

        self.history.append((current_time, success))
        
        self._clean_old_entries()
    
    def check_health(self):
        if self.consecutive_failures >= self.max_consecutive_failures:
            raise APIHealthError(
                f"OpenAlex API appears to be down - "
                f"{self.consecutive_failures} consecutive failures"
            )
        
        self._clean_old_entries()
        
        if len(self.history) < self.min_attempts:
            return
        
        total_attempts = len(self.history)
        failures = sum(1 for _, success in self.history if not success)
        error_rate = failures / total_attempts
        
        if error_rate >= self.max_error_rate:
            raise APIHealthError(
                f"OpenAlex API health check failed - "
                f"{failures}/{total_attempts} failures ({error_rate:.1%}) in last {self.window_seconds}s"
            )
    
    def get_stats(self):
        self._clean_old_entries()
        
        if not self.history:
            return "No recent attempts"
        
        total = len(self.history)
        failures = sum(1 for _, success in self.history if not success)
        success_rate = (total - failures) / total * 100
        
        return f"{total} attempts, {success_rate:.1f}% success rate"


def timer_decorator(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        elapsed_time = time.time() - start_time
        if elapsed_time > 1:
            logging.debug(f"{func.__name__} took {elapsed_time:.2f} seconds")
        return result
    return wrapper


class OpenAlexClient:
    BASE_URL = "https://api.openalex.org"
    
    def __init__(self, mailto, similarity_threshold=95,
                 error_tracking_config=None):
        self.mailto = mailto
        self.similarity_threshold = similarity_threshold
        
        if error_tracking_config:
            self.error_tracker = APIErrorTracker(**error_tracking_config)
        else:
            self.error_tracker = APIErrorTracker()
        
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'OpenAlex Works Matching/1.0'
        })
    
    @sleep_and_retry
    @limits(calls=10, period=1)
    def _make_request(self, url, params=None,
                     max_retries=3, retry_delay=10):

        if params is None:
            params = {}
        
        params['mailto'] = self.mailto
        
        for attempt in range(max_retries):
            try:
                response = self.session.get(url, params=params, timeout=30)
                
                if response.status_code == 200:
                    self.error_tracker.record_attempt(True)
                    return response.json()
                elif response.status_code == 404:
                    self.error_tracker.record_attempt(True)
                    return None
                elif response.status_code == 429:
                    logging.warning(f"Rate limit hit, waiting {retry_delay * 2} seconds")
                    time.sleep(retry_delay * 2)
                    continue
                else:
                    logging.warning(f"OpenAlex API error: {response.status_code}")
                    self.error_tracker.record_attempt(False)
                    
            except requests.exceptions.Timeout:
                logging.warning(f"OpenAlex API timeout (attempt {attempt + 1}/{max_retries})")
                self.error_tracker.record_attempt(False)
            except requests.exceptions.RequestException as e:
                logging.warning(f"OpenAlex API request error: {e}")
                self.error_tracker.record_attempt(False)
            except Exception as e:
                logging.error(f"Unexpected error in OpenAlex API call: {e}")
                self.error_tracker.record_attempt(False)
            try:
                self.error_tracker.check_health()
            except APIHealthError as e:
                logging.error(f"API health check failed: {e}")
                raise
            
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
        
        return None
    
    @timer_decorator
    def search_for_work(self, title, max_results=10):
        if not title:
            return None
        
        original_title = title
        cleaned_title = clean_title_for_search(title, aggressive=False)
        logging.debug(f"Strategy 1 - Searching with cleaned title: {cleaned_title}")
        
        result = self._search_and_match(cleaned_title, original_title, max_results, "cleaned_title")
        if result:
            return result

        words = cleaned_title.split()
        if len(words) > 10:
            truncated_title = ' '.join(words[:10])
            logging.debug(f"Strategy 2 - Searching with truncated title: {truncated_title}")
            result = self._search_and_match(truncated_title, original_title, max_results, "truncated_title")
            if result:
                return result

        aggressive_title = clean_title_for_search(title, aggressive=True)
        if aggressive_title != cleaned_title:
            logging.debug(f"Strategy 3 - Searching with aggressive normalization: {aggressive_title}")
            result = self._search_and_match(aggressive_title, original_title, max_results, "aggressive_normalization")
            if result:
                return result
        
        logging.debug(f"Strategy 4 - Searching with raw title: {original_title}")
        result = self._search_and_match(original_title, original_title, max_results, "raw_title")
        if result:
            return result
        
        logging.info(f"No match found for title: {original_title[:100]}")
        return None
    
    def _search_and_match(self, search_title, original_title,
                         max_results, method):
        url = f"{self.BASE_URL}/works"
        params = {
            'search': search_title,
            'per_page': max_results
        }
        
        data = self._make_request(url, params)
        if not data or 'results' not in data:
            return None
        
        results = data.get('results', [])
        if not results:
            return None
        
        best_match = None
        best_ratio = 0
        
        normalized_search = normalize_text(original_title)
        
        for work in results:
            work_title = work.get('title', '')
            if not work_title:
                continue
            
            normalized_work = normalize_text(work_title)
            
            ratio = fuzz.ratio(normalized_search, normalized_work)
            
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = work
        
        if best_match and best_ratio >= self.similarity_threshold:
            logging.info(f"Found match with {best_ratio}% similarity using {method}")
            return best_match, best_ratio, method
        
        return None
    
    @timer_decorator
    def fetch_work_by_id(self, work_id):
        if work_id.startswith('https://openalex.org/'):
            work_id = work_id.replace('https://openalex.org/', '')
        
        url = f"{self.BASE_URL}/works/{work_id}"
        return self._make_request(url)
    
    def extract_metadata(self, work_data, target_funder_ids=None, 
                        award_id=None):
        metadata = {
            'openalex_work_id': work_data.get('id', ''),
            'publication_title': work_data.get('title', ''),
            'publication_year': work_data.get('publication_year'),
            'publication_date': work_data.get('publication_date'),
            'doi': work_data.get('doi', ''),
            'type': work_data.get('type', ''),
            'language': work_data.get('language', ''),
            'cited_by_count': work_data.get('cited_by_count', 0),
            'is_retracted': work_data.get('is_retracted', False),
            'metadata_source': 'openalex'
        }
        
        authorships = work_data.get('authorships', [])
        if authorships:
            authors_list = []
            for authorship in authorships:
                author = authorship.get('author', {})
                author_name = author.get('display_name', '')
                if author_name:
                    authors_list.append(author_name)
            metadata['authors'] = '; '.join(authors_list)
            metadata['authors_count'] = len(authors_list)
        else:
            metadata['authors'] = ''
            metadata['authors_count'] = 0
        
        primary_location = work_data.get('primary_location') or {}
        if primary_location:
            source = primary_location.get('source') or {}
            metadata['journal'] = source.get('display_name', '') if source else ''
            metadata['issn'] = source.get('issn_l', '') if source else ''
            metadata['publisher'] = source.get('host_organization_name', '') if source else ''
            metadata['volume'] = primary_location.get('volume', '') if primary_location else ''
            metadata['issue'] = primary_location.get('issue', '') if primary_location else ''
            metadata['pages'] = primary_location.get('pages', '') if primary_location else ''
        else:
            metadata['journal'] = ''
            metadata['issn'] = ''
            metadata['publisher'] = ''
            metadata['volume'] = ''
            metadata['issue'] = ''
            metadata['pages'] = ''
        
        open_access = work_data.get('open_access') or {}
        metadata['oa_status'] = open_access.get('oa_status', '') if open_access else ''
        metadata['is_oa'] = open_access.get('is_oa', False) if open_access else False
        metadata['oa_url'] = open_access.get('oa_url', '') if open_access else ''
        
        best_oa_location = work_data.get('best_oa_location') or {}
        if best_oa_location:
            metadata['best_oa_landing_page_url'] = best_oa_location.get('landing_page_url', '') if best_oa_location else ''
            metadata['best_oa_pdf_url'] = best_oa_location.get('pdf_url', '') if best_oa_location else ''
            metadata['best_oa_license'] = best_oa_location.get('license', '') if best_oa_location else ''
            metadata['best_oa_version'] = best_oa_location.get('version', '') if best_oa_location else ''
        else:
            metadata['best_oa_landing_page_url'] = ''
            metadata['best_oa_pdf_url'] = ''
            metadata['best_oa_license'] = ''
            metadata['best_oa_version'] = ''
        
        if target_funder_ids:
            funder_results = self._check_funders_presence(work_data, target_funder_ids)
            metadata.update(funder_results)
        
        grants = work_data.get('grants', [])
        if grants:
            grant_info = []
            for grant in grants:
                funder = grant.get('funder_display_name', '')
                award = grant.get('award_id', '')
                if funder or award:
                    grant_str = f"{funder}: {award}" if award else funder
                    grant_info.append(grant_str)
            metadata['funding_info'] = '; '.join(grant_info)
            metadata['funding_count'] = len(grants)
        else:
            metadata['funding_info'] = ''
            metadata['funding_count'] = 0
        
        if award_id:
            metadata.update(self._check_award_id_match(work_data, award_id))
        
        topics = work_data.get('topics', [])
        if topics:
            topic_names = [t.get('display_name', '') for t in topics if t.get('display_name')]
            metadata['topics'] = '; '.join(topic_names[:5])
        
        abstract_inverted_index = work_data.get('abstract_inverted_index', {})
        if abstract_inverted_index:
            words = [''] * (max(max(positions) for positions in abstract_inverted_index.values()) + 1)
            for word, positions in abstract_inverted_index.items():
                for pos in positions:
                    words[pos] = word
            metadata['abstract'] = ' '.join(words).strip()
        
        return metadata
    
    def _normalize_award_id(self, award_id):
        if not award_id:
            return ""
        
        normalized = award_id.lower()
        normalized = normalized.replace(' ', '').replace('.', '').replace('-', '').replace('_', '')
        normalized = normalized.replace('grant', '').replace('award', '').replace('#', '')
        
        return normalized
    
    def _check_award_id_match(self, work_data, award_id):
        result = {
            'award_id_match': False,
            'award_id_match_type': None,
            'award_id_match_score': 0,
            'matched_grant_award_id': None,
            'matched_grant_funder': None
        }
        
        if not award_id:
            return result
        
        normalized_input = self._normalize_award_id(award_id)
        grants = work_data.get('grants', [])
        
        best_match = None
        best_score = 0
        best_match_type = None
        
        for grant in grants:
            grant_award_id = grant.get('award_id', '')
            if not grant_award_id:
                continue

            if award_id == grant_award_id:
                result['award_id_match'] = True
                result['award_id_match_type'] = 'exact'
                result['award_id_match_score'] = 100
                result['matched_grant_award_id'] = grant_award_id
                result['matched_grant_funder'] = grant.get('funder_display_name', '')
                return result

            normalized_grant = self._normalize_award_id(grant_award_id)
            if normalized_input == normalized_grant:
                best_match = grant
                best_score = 95
                best_match_type = 'normalized'
                continue

            if normalized_input and normalized_grant:
                if normalized_input in normalized_grant or normalized_grant in normalized_input:
                    score = 85
                    if score > best_score:
                        best_match = grant
                        best_score = score
                        best_match_type = 'contains'
                else:
                    score = fuzz.ratio(normalized_input, normalized_grant)
                    if score > best_score and score >= 70:
                        best_match = grant
                        best_score = score
                        best_match_type = 'fuzzy'
        
        if best_match:
            result['award_id_match'] = True
            result['award_id_match_type'] = best_match_type
            result['award_id_match_score'] = best_score
            result['matched_grant_award_id'] = best_match.get('award_id', '')
            result['matched_grant_funder'] = best_match.get('funder_display_name', '')
        
        return result
    
    def _check_funders_presence(self, work_data, target_funder_ids):
        results = {
            'has_any_target_funder': False,
            'matched_target_funders': [],
            'matched_target_funder_names': [],
            'target_funder_match_count': 0
        }
        
        results['has_target_funder'] = False
        
        if not target_funder_ids:
            return results
        
        grants = work_data.get('grants', [])
        matched_funders = set()
        matched_funder_names = set()
        
        for grant in grants:
            funder_id = grant.get('funder', '')
            if funder_id in target_funder_ids:
                matched_funders.add(funder_id)
                funder_name = grant.get('funder_display_name', '')
                if funder_name:
                    matched_funder_names.add(funder_name)
        
        if matched_funders:
            results['has_any_target_funder'] = True
            results['has_target_funder'] = True
            results['matched_target_funders'] = list(matched_funders)
            results['matched_target_funder_names'] = list(matched_funder_names)
            results['target_funder_match_count'] = len(matched_funders)
        
        return results