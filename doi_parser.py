import re
import logging
from urllib.parse import unquote, urlparse


def extract_doi(url_string):
    if not url_string:
        return None
    
    url_string = str(url_string).strip()
    try:
        url_string = unquote(url_string)
    except:
        pass
    
    doi_pattern = r'10\.\d{4,}(?:\.\d+)*\/[-._;()\/:A-Za-z0-9]+'
    match = re.search(doi_pattern, url_string)
    if match:
        doi = match.group(0)
        logging.debug(f"Extracted DOI via direct pattern match: {doi}")
        return doi
    
    common_prefixes = [
        'https://doi.org/',
        'http://doi.org/',
        'https://dx.doi.org/',
        'http://dx.doi.org/',
        'doi.org/',
        'dx.doi.org/',
        'doi:',
        'DOI:',
        'https://link.springer.com/article/',
        'https://link.springer.com/chapter/',
        'https://www.nature.com/articles/',
        'https://science.sciencemag.org/content/',
        'https://pubs.acs.org/doi/',
        'https://onlinelibrary.wiley.com/doi/',
        'https://journals.plos.org/plosone/article?id=',
    ]
    
    for prefix in common_prefixes:
        if prefix.lower() in url_string.lower():
            idx = url_string.lower().index(prefix.lower()) + len(prefix)
            potential_doi = url_string[idx:]
            potential_doi = potential_doi.split('?')[0].split('#')[0]
            
            match = re.match(doi_pattern, potential_doi)
            if match:
                doi = match.group(0)
                logging.debug(f"Extracted DOI after prefix '{prefix}': {doi}")
                return doi
    
    try:
        parsed = urlparse(url_string)
        path = parsed.path
        
        if path.startswith('/'):
            path = path[1:]
        
        match = re.search(doi_pattern, path)
        if match:
            doi = match.group(0)
            logging.debug(f"Extracted DOI from URL path: {doi}")
            return doi
        
        if parsed.query:
            match = re.search(doi_pattern, parsed.query)
            if match:
                doi = match.group(0)
                logging.debug(f"Extracted DOI from URL query: {doi}")
                return doi
    except:
        pass
    
    logging.debug(f"No DOI found in: {url_string[:100]}")
    return None


def is_valid_doi(doi_string):
    if not doi_string:
        return False
    
    doi_pattern = r'^10\.\d{4,}(?:\.\d+)*\/[-._;()\/:A-Za-z0-9]+$'
    return bool(re.match(doi_pattern, doi_string))