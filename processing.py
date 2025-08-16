import logging
from thefuzz import fuzz
from title_normalizer import extract_date_from_title, extract_main_title, clean_title_for_search
from openalex_client import OpenAlexClient
from author_affiliation_matcher import AuthorAffiliationMatcher


class ProcessingEngine:
    def __init__(self, config, openalex_client):
        self.config = config
        self.openalex_client = openalex_client
        self.target_funder_ids = config.get_target_funder_ids()
    
    def process_record(self, raw_record):
        result = dict(raw_record)
        title = raw_record.get('title', '')
        if not title:
            logging.warning(f"No title found for record: {raw_record.get('award_id', 'unknown')}")
            result['metadata_source'] = 'no_title'
            result['match_status'] = 'failed'
            return [result]
        
        cleaned_title, extracted_date, date_format = extract_date_from_title(title)
        main_title = extract_main_title(cleaned_title)
        search_title = clean_title_for_search(title)
        
        result['cleaned_title'] = search_title
        result['extracted_date'] = extracted_date
        result['date_format'] = date_format
        
        input_year = raw_record.get('year')
        
        logging.info(f"Searching for: {title[:100]}")
        search_result = self.openalex_client.search_for_work(title, year=input_year)
        
        if not search_result:
            logging.info(f"No match found for: {title[:100]}")
            result['metadata_source'] = 'not_found'
            result['match_status'] = 'no_match'
            result['match_ratio'] = 0
            return [result]
        
        work_data, match_ratio, search_method = search_result
        
        result['match_status'] = 'matched'
        result['match_ratio'] = match_ratio
        result['search_method'] = search_method
        result['matched_title'] = work_data.get('title', '')
        
        award_id = raw_record.get('award_id')
        metadata = self.openalex_client.extract_metadata(work_data, self.target_funder_ids, award_id)
        
        result.update(metadata)
        
        input_authors = raw_record.get('authors')
        if input_authors and metadata.get('authors'):
            author_match_result = self._match_authors(input_authors, metadata['authors'])
            result.update(author_match_result)
        
        input_year = raw_record.get('year')
        if input_year and metadata.get('publication_year'):
            year_match_result = self._validate_year(input_year, metadata['publication_year'])
            result.update(year_match_result)
        
        return [result]
    
    def _match_authors(self, input_authors, publication_authors):
        result = {
            'matched_authors': False,
            'matched_authors_count': 0,
            'matched_authors_list': ''
        }
        
        input_lastnames = self._extract_lastnames(input_authors)
        if not input_lastnames:
            return result
        
        pub_lastnames = self._extract_lastnames(publication_authors)
        if not pub_lastnames:
            return result
        
        matched = []
        for input_name in input_lastnames:
            for pub_name in pub_lastnames:
                if fuzz.ratio(input_name.lower(), pub_name.lower()) >= 85:
                    matched.append(input_name)
                    break
        
        if matched:
            result['matched_authors'] = True
            result['matched_authors_count'] = len(matched)
            result['matched_authors_list'] = '; '.join(matched)
        
        return result
    
    def _extract_lastnames(self, authors):
        lastnames = []
        
        if isinstance(authors, str):
            for author in authors.split(';'):
                author = author.strip()
                if ',' in author:
                    lastname = author.split(',')[0].strip()
                else:
                    parts = author.split()
                    if parts:
                        lastname = parts[-1]
                    else:
                        continue
                lastnames.append(lastname)
        
        elif isinstance(authors, list):
            for author in authors:
                if isinstance(author, dict):
                    lastname = author.get('last_name', '')
                    if not lastname:
                        lastname = author.get('family', '')
                    if lastname:
                        lastnames.append(lastname)
                elif isinstance(author, str):
                    if ',' in author:
                        lastname = author.split(',')[0].strip()
                    else:
                        parts = author.split()
                        if parts:
                            lastname = parts[-1]
                        else:
                            continue
                    lastnames.append(lastname)
        
        return lastnames
    
    def _validate_year(self, input_year, publication_year):
        result = {
            'year_match': False,
            'year_difference': None
        }
        
        try:
            input_year_int = int(input_year)
            pub_year_int = int(publication_year)
        except (ValueError, TypeError):
            return result
        
        year_diff = abs(input_year_int - pub_year_int)
        result['year_difference'] = year_diff
        
        result['year_match'] = year_diff <= 1
        
        return result


class AuthorAffiliationProcessor:
    
    def __init__(self, config, openalex_client, embedding_model=None):
        self.config = config
        self.openalex_client = openalex_client
        self.target_funder_ids = config.get_target_funder_ids()
        
        self.author_style = config.get_author_name_style()
        self.author_separator = config.get_author_separator()
        self.name_threshold = config.get_name_matching_threshold()
        self.affiliation_threshold = config.get_affiliation_matching_threshold()
        self.max_results_per_author = config.get_max_results_per_author()
        self.year_window = config.get_year_search_window()
        self.author_weight = config.get_author_weight()
        self.affiliation_weight = config.get_affiliation_weight()
        self.minimum_affiliation_score = config.get_minimum_affiliation_score()
        self.use_institution_search = config.use_institution_search()
        self.use_ror_api = config.use_ror_api()
        
        if embedding_model:
            self.affiliation_threshold = config.get_embedding_similarity_threshold()
        
        self.matcher = AuthorAffiliationMatcher(
            name_matching_threshold=self.name_threshold,
            embedding_model=embedding_model
        )
        self.embedding_model = embedding_model
    
    def process_record(self, raw_record):
        authors = raw_record.get('authors', '')
        affiliation = raw_record.get('affiliation', '')
        year = raw_record.get('year')
        award_id = raw_record.get('award_id')
        
        if not authors or not affiliation:
            logging.warning(f"Missing authors or affiliation for record: {award_id}")
            result = dict(raw_record)
            result['metadata_source'] = 'missing_required_fields'
            result['match_status'] = 'failed'
            result['match_method'] = 'author_affiliation'
            return [result]
        
        author_list = self.matcher.parse_authors_list(
            authors, 
            separator=self.author_separator,
            name_style=self.author_style
        )
        
        if not author_list:
            logging.warning(f"Could not parse authors for record: {award_id}")
            result = dict(raw_record)
            result['metadata_source'] = 'parse_error'
            result['match_status'] = 'failed'
            result['match_method'] = 'author_affiliation'
            return [result]
        
        all_matched_works = []
        
        for parsed_author in author_list:
            author_name = parsed_author['original']
            logging.info(f"Searching for works by {author_name} at {affiliation}")
            
            matched_works = self.openalex_client.search_by_author_affiliation(
                author_name=author_name,
                affiliation=affiliation,
                year=year,
                author_style=self.author_style,
                name_threshold=self.name_threshold,
                affiliation_threshold=self.affiliation_threshold,
                max_results=self.max_results_per_author,
                embedding_model=self.embedding_model,
                year_window=self.year_window,
                author_weight=self.author_weight,
                affiliation_weight=self.affiliation_weight,
                minimum_affiliation_score=self.minimum_affiliation_score,
                use_institution_search=self.use_institution_search,
                use_ror_api=self.use_ror_api
            )
            
            if matched_works:
                all_matched_works.extend(matched_works)
        
        if not all_matched_works:
            logging.info(f"No matching works found for authors at {affiliation}")
            result = dict(raw_record)
            result['metadata_source'] = 'not_found'
            result['match_status'] = 'no_match'
            result['match_method'] = 'author_affiliation'
            result['author_match_score'] = 0
            result['affiliation_match_score'] = 0
            return [result]
        
        results = []
        
        all_matched_works.sort(key=lambda x: x['combined_score'], reverse=True)
        
        logging.info(f"Creating {len(all_matched_works)} result rows for {award_id}")
        
        for match in all_matched_works:
            result = dict(raw_record)
            
            work_data = match['work']
            
            result['match_status'] = 'matched'
            result['match_method'] = 'author_affiliation'
            result['matched_author'] = match['matched_author']
            result['matched_author_id'] = match.get('matched_author_id', '')
            result['matched_author_orcid'] = match.get('matched_author_orcid', '')
            result['matched_affiliation'] = match['matched_affiliation']
            result['matched_affiliation_id'] = match.get('matched_affiliation_id', '')
            result['matched_affiliation_ror'] = match.get('matched_affiliation_ror', '')
            result['author_match_score'] = match['author_match_score']
            result['affiliation_match_score'] = match['affiliation_match_score']
            result['combined_match_score'] = match['combined_score']
            
            metadata = self.openalex_client.extract_metadata(work_data, self.target_funder_ids, award_id)
            
            if 'authors' in metadata:
                metadata['work_authors'] = metadata['authors']
                del metadata['authors']
            
            result.update(metadata)
            
            input_year = raw_record.get('year')
            if input_year and metadata.get('publication_year'):
                year_match_result = self._validate_year(input_year, metadata['publication_year'])
                result.update(year_match_result)
            
            results.append(result)
        
        return results
    
    def _validate_year(self, input_year, publication_year):
        result = {
            'year_match': False,
            'year_difference': None
        }
        
        try:
            input_year_int = int(input_year)
            pub_year_int = int(publication_year)
        except (ValueError, TypeError):
            return result
        
        year_diff = pub_year_int - input_year_int
        result['year_difference'] = year_diff
        
        if self.year_window is not None:
            result['year_match'] = 0 <= year_diff <= self.year_window
        else:
            result['year_match'] = year_diff >= 0
        
        return result