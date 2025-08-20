import re
from datetime import datetime
from unidecode import unidecode
from nltk.corpus import stopwords
import nltk

try:
    nltk.data.find('corpora/stopwords')
except LookupError:
    nltk.download('stopwords', quiet=True)


def parse_date_string(date_str):
    if not date_str:
        return None, None
    
    date_str = date_str.strip()

    months = {
        'january': 1, 'jan': 1, 'jan.': 1,
        'february': 2, 'feb': 2, 'feb.': 2,
        'march': 3, 'mar': 3, 'mar.': 3,
        'april': 4, 'apr': 4, 'apr.': 4,
        'may': 5,
        'june': 6, 'jun': 6, 'jun.': 6,
        'july': 7, 'jul': 7, 'jul.': 7,
        'august': 8, 'aug': 8, 'aug.': 8,
        'september': 9, 'sep': 9, 'sep.': 9, 'sept': 9, 'sept.': 9,
        'october': 10, 'oct': 10, 'oct.': 10,
        'november': 11, 'nov': 11, 'nov.': 11,
        'december': 12, 'dec': 12, 'dec.': 12
    }
    
    patterns = [
        (r'^(\d{1,2})\s+([A-Za-z]+\.?)\s+(\d{4})$', 'full_date'),
        (r'^(\d{1,2})-\d{1,2}\s+([A-Za-z]+\.?)\s+(\d{4})$', 'date_range'),
        (r'^([A-Za-z]+\.?)\s+(\d{4})$', 'month_year'),
        (r'^(\d{1,2})\s+([A-Za-z]+\.?)\s+(\d{4})$', 'abbreviated'),
    ]
    
    for pattern, date_format in patterns:
        match = re.match(pattern, date_str, re.IGNORECASE)
        if match:
            if date_format in ['full_date', 'date_range', 'abbreviated']:
                day = match.group(1)
                month_str = match.group(2).lower().rstrip('.')
                year = match.group(3)
                
                month_num = months.get(month_str)
                if month_num:
                    try:
                        parsed = datetime(int(year), month_num, int(day))
                        return parsed.strftime('%Y-%m-%d'), date_format
                    except ValueError:
                        pass
                        
            elif date_format == 'month_year':
                month_str = match.group(1).lower().rstrip('.')
                year = match.group(2)
                
                month_num = months.get(month_str)
                if month_num:
                    try:
                        parsed = datetime(int(year), month_num, 1)
                        return parsed.strftime('%Y-%m'), date_format
                    except ValueError:
                        pass
    
    return None, None


def extract_date_from_title(title):
    if not title:
        return title, None, None
    
    original_title = title
    extracted_date = None
    date_format = None
    
    # Pattern 1: Date at the beginning followed by comma or period
    # Examples: "9 July 2019, Title..." or "28 November 2018. Title..."
    beginning_date_pattern = r'^((?:\d{1,2}[-–]\d{1,2}\s+)?(?:\d{1,2}\s+)?[A-Za-z]+\.?\s+\d{4})[,.]?\s+'
    match = re.match(beginning_date_pattern, title)
    if match:
        date_str = match.group(1)
        parsed_date, format_type = parse_date_string(date_str)
        if parsed_date:
            extracted_date = parsed_date
            date_format = format_type
            title = title[match.end():].strip()
            return title, extracted_date, date_format
    
    # Pattern 2: Date at the end in parentheses
    # Examples: "Title (March 2017)" or "Title (23 Oct. 2020)"
    end_date_pattern = r'\s*\(((?:\d{1,2}[-–]\d{1,2}\s+)?(?:\d{1,2}\s+)?[A-Za-z]+\.?\s+\d{4})\)\s*$'
    match = re.search(end_date_pattern, title)
    if match:
        date_str = match.group(1)
        parsed_date, format_type = parse_date_string(date_str)
        if parsed_date:
            extracted_date = parsed_date
            date_format = format_type
            title = title[:match.start()].strip()
            return title, extracted_date, date_format
    
    # Pattern 3: Date in the middle separated by colons or dashes
    # Examples: "Event Name: 15 June 2018: Subtitle" or "Conference - May 2019 - Topic"
    middle_date_pattern = r'[-:]\s*((?:\d{1,2}[-–]\d{1,2}\s+)?(?:\d{1,2}\s+)?[A-Za-z]+\.?\s+\d{4})\s*[-:]'
    match = re.search(middle_date_pattern, title)
    if match:
        date_str = match.group(1)
        parsed_date, format_type = parse_date_string(date_str)
        if parsed_date:
            extracted_date = parsed_date
            date_format = format_type
            title = title[:match.start(1)] + title[match.end(1):]
            title = re.sub(r'[-:]\s*[-:]', ':', title).strip()
            return title, extracted_date, date_format
    
    return original_title, None, None


def normalize_text(text, aggressive=False):
    if not text:
        return ""
    
    text = text.lower()
    text = unidecode(text)
    text = re.sub(r'&[a-z]+;', ' ', text)
    text = re.sub(r'[-_]', ' ', text)
    text = re.sub(r'[^\w\s]', ' ', text)
    text = ' '.join(text.split())
    
    if aggressive:
        try:
            stop_words = set(stopwords.words('english'))
            words = text.split()
            text = ' '.join([w for w in words if w not in stop_words])
        except:
            pass
    
    return text.strip()


def extract_main_title(title):
    if not title:
        return ""
    
    original = title
    
    title, _, _ = extract_date_from_title(title)
    
    end_patterns = [
        r'\s*\[.*?\]\s*$',           # Remove content in square brackets at the end
        r'\s*\(.*?\)\s*$',           # Remove content in parentheses at the end
        r'\s+[-–—]\s+.*$',           # Remove everything after dash (subtitle)
        r'\s*[:]\s+.*$',             # Remove everything after colon (subtitle)
        r'\s+[A-Z]{2,}[-\d]+$',     # Remove report/document numbers (e.g., "NASA-TM-12345")
        r'\s+\d{4}[-/]\d+$',         # Remove year/number identifiers
        r'\s+v\d+$',                 # Remove version numbers (v1, v2, etc.)
        r'\s+vol[\s.]+\d+.*$',       # Remove volume information
        r'\s+part[\s.]+[IVX\d]+.*$', # Remove part information
        r'\s+chapter[\s.]+\d+.*$',   # Remove chapter information
        r'\s+\(?abstract\)?$',       # Remove "abstract" suffix
        r'\s+\(?summary\)?$',        # Remove "summary" suffix
        r'\s+\(?preprint\)?$',       # Remove "preprint" suffix
        r'\s+\(?poster\)?$',         # Remove "poster" suffix
        r'\s+\(?presentation\)?$',   # Remove "presentation" suffix
        r'\s+\(?paper\)?$',          # Remove "paper" suffix
        r'\s+\(?thesis\)?$',         # Remove "thesis" suffix
        r'\s+\(?dissertation\)?$',   # Remove "dissertation" suffix
        r'\s+\(?conference\)?$',     # Remove "conference" suffix
        r'\s+\(?proceedings?\)?$',   # Remove "proceeding(s)" suffix
        r'\s+\(?workshop\)?$',       # Remove "workshop" suffix
        r'\s+\(?symposium\)?$',      # Remove "symposium" suffix
        r'\s+\(?extended\)?$',       # Remove "extended" suffix
        r'\s+\(?revised\)?$',        # Remove "revised" suffix
        r'\s+\(?updated\)?$',        # Remove "updated" suffix
        r'\s+\(?final\)?$',          # Remove "final" suffix
        r'\s+\(?draft\)?$',          # Remove "draft" suffix
        r'\s*[.?!]+$',               # Remove trailing punctuation
    ]
    
    for pattern in end_patterns:
        title = re.sub(pattern, '', title, flags=re.IGNORECASE)
    
    if ';' in title:
        title = title.split(';')[0]
    
    title = ' '.join(title.split())

    if not title:
        return original
    
    return title.strip()


def sanitize_for_openalex_search(title):
    if not title:
        return ""
    
    title = title.translate(str.maketrans('|+', '  ', '*?~^\\{}[]'))
    title = ' '.join(title.split())
    
    return title.strip()


def clean_title_for_search(title, aggressive=False):
    if not title:
        return ""
    
    title, _, _ = extract_date_from_title(title)
    title = extract_main_title(title)
    title = normalize_text(title, aggressive=aggressive)
    
    return title