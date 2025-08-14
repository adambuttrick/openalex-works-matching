import logging
from thefuzz import fuzz
from title_normalizer import extract_date_from_title, extract_main_title, clean_title_for_search
from openalex_client import OpenAlexClient


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
            return result
        
        cleaned_title, extracted_date, date_format = extract_date_from_title(title)
        main_title = extract_main_title(cleaned_title)
        search_title = clean_title_for_search(title)
        
        result['cleaned_title'] = search_title
        result['extracted_date'] = extracted_date
        result['date_format'] = date_format
        
        logging.info(f"Searching for: {title[:100]}")
        search_result = self.openalex_client.search_for_work(title)
        
        if not search_result:
            logging.info(f"No match found for: {title[:100]}")
            result['metadata_source'] = 'not_found'
            result['match_status'] = 'no_match'
            result['match_ratio'] = 0
            return result
        
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
        
        return result
    
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