import re
import unicodedata
import logging
import jellyfish
from unidecode import unidecode
from nameparser import HumanName
from typing import Optional


class AuthorAffiliationMatcher:
    # Common surname prefixes that should be kept together
    SURNAME_PREFIXES = {
        'de', 'del', 'della', 'di', 'da',
        'van', 'von', 'der', 'den', 'ter',
        'le', 'la', 'les', 'du', 'des',
        'mac', 'mc', "o'", "d'",
        'al', 'el', 'ibn', 'bin', 'abu',
        'dos', 'das', 'do',
        'san', 'santa', 'santo',
        'st', 'saint'
    }
    
    def __init__(self, name_matching_threshold=0.85, embedding_model=None):
        self.name_matching_threshold = name_matching_threshold
        self.embedding_model = embedding_model

    @staticmethod
    def is_likely_initial(token):
        if not token:
            return False
        clean_token = token.replace('.', '').strip()
        return (len(clean_token) == 1 or 
                (len(clean_token) <= 3 and clean_token.isupper()))
    
    @classmethod
    def is_surname_prefix(cls, token):
        return token.lower() in cls.SURNAME_PREFIXES
    
    @classmethod
    def parse_compound_surname_with_initial(cls, name_parts):
        if not name_parts:
            return [], []
        
        if cls.is_likely_initial(name_parts[-1]):
            initial_parts = [name_parts[-1]]
            surname_parts = name_parts[:-1]
        else:
            surname_parts = name_parts
            initial_parts = []
        
        if len(surname_parts) > 1:
            surname_str = ' '.join(surname_parts)
            surname_parts = [surname_str]
        
        return surname_parts, initial_parts
    
    @staticmethod
    def is_latin_char_text(text):
        if not isinstance(text, str):
            return False
        for char in text:
            if '\u0000' <= char <= '\u024F':
                return True
        return False

    @staticmethod
    def normalize_text(text):
        if not isinstance(text, str):
            return text

        if AuthorAffiliationMatcher.is_latin_char_text(text):
            text = unidecode(text)

        text = text.lower()
        text = re.sub(r'[^\w\s]', '', text)
        text = text.strip()
        return text

    @staticmethod
    def extract_surname(name: str, style: str) -> str:
        if not name:
            return ''
        
        name = name.strip()
        
        if style == 'last_initial':
            # Format: "Smith J" or "De La Cruz Pech-Canul Á"
            parts = name.split()
            if len(parts) >= 2:
                surname_parts, _ = AuthorAffiliationMatcher.parse_compound_surname_with_initial(parts)
                return ' '.join(surname_parts) if surname_parts else parts[0]
            return name
            
        elif style == 'last_comma_first':
            # Format: "Smith, John"
            if ',' in name:
                return name.split(',')[0].strip()
            return name
            
        elif style == 'last_first':
            # Format: "Smith John"
            parts = name.split()
            if parts:
                return parts[0]
            return name
            
        elif style == 'first_initial_last':
            # Format: "J. Smith" or "J Smith"
            parts = name.split()
            # Skip initials at the beginning
            for i, part in enumerate(parts):
                if not (len(part) <= 2 and (part.endswith('.') or len(part) == 1)):
                    # This is likely the start of the surname
                    return ' '.join(parts[i:])
            return parts[-1] if parts else name
            
        else:  # 'first_last' or 'auto'
            # Format: "John Smith" - take the last word(s)
            parsed = HumanName(name)
            return parsed.last or name.split()[-1] if name.split() else name
    
    @staticmethod
    def parse_name_by_style(name: str, style: str) -> dict:
        name = name.strip()

        if style == 'last_initial':
            # Format: "Smith J" or "De La Cruz Pech-Canul Á"
            parts = name.split()
            
            if len(parts) >= 2:
                surname_parts, initial_parts = AuthorAffiliationMatcher.parse_compound_surname_with_initial(parts)
                last_name = ' '.join(surname_parts) if surname_parts else name
                
                if initial_parts:
                    initials = initial_parts[0]
                    first_initial = initials[0].lower() if initials else ''
                else:
                    first_initial = ''
                    initials = ''
                
                return {
                    'first': first_initial,
                    'last': last_name.lower(),
                    'middle': '',
                    'normalized': f"{last_name.lower()} {first_initial}".strip(),
                    'original': name,
                    'style': style
                }
            else:
                return {
                    'first': '',
                    'last': name.lower(),
                    'middle': '',
                    'normalized': name.lower(),
                    'original': name,
                    'style': style
                }

        elif style == 'last_comma_first':
            # Format: "Smith, John"
            if ',' in name:
                parts = name.split(',', 1)
                last = parts[0].strip()
                rest = parts[1].strip() if len(parts) > 1 else ''

                rest_parts = rest.split()
                first = rest_parts[0].lower() if rest_parts else ''
                middle = ' '.join(rest_parts[1:]).lower() if len(
                    rest_parts) > 1 else ''

                return {
                    'first': first,
                    'last': last.lower(),
                    'middle': middle,
                    'normalized': f"{first} {middle} {last.lower()}".strip(),
                    'original': name,
                    'style': style
                }

        elif style == 'last_first':
            # Format: "Smith John"
            parts = name.split()
            if len(parts) >= 2:
                last = parts[0]
                first = parts[1] if len(parts) > 1 else ''
                middle = ' '.join(parts[2:]) if len(parts) > 2 else ''

                return {
                    'first': first.lower(),
                    'last': last.lower(),
                    'middle': middle.lower(),
                    'normalized': f"{first.lower()} {middle.lower()} {last.lower()}".strip(),
                    'original': name,
                    'style': style
                }

        elif style == 'first_initial_last':
            # Format: "J. Smith" or "J Smith"
            parts = name.split()
            initials = []
            last_idx = -1

            for i, part in enumerate(parts):
                if len(part) <= 2 and (part.endswith('.') or len(part) == 1):
                    initials.append(part.replace('.', '').lower())
                else:
                    last_idx = i
                    break

            if last_idx >= 0:
                last = ' '.join(parts[last_idx:])
                first = initials[0] if initials else ''
                middle = ' '.join(initials[1:]) if len(initials) > 1 else ''

                return {
                    'first': first,
                    'last': last.lower(),
                    'middle': middle,
                    'normalized': f"{first} {middle} {last.lower()}".strip(),
                    'original': name,
                    'style': style
                }

        parsed = HumanName(name)
        first = (parsed.first or '').strip()
        last = (parsed.last or '').strip()
        middle = (parsed.middle or '').strip()

        clean = f"{first} {middle} {last}".strip()
        clean = unicodedata.normalize('NFKD', clean).encode(
            'ascii', 'ignore').decode()
        normalized = re.sub(r'[-.,]', ' ', clean.lower()).strip()

        return {
            'first': first.lower(),
            'last': last.lower(),
            'middle': middle.lower(),
            'normalized': normalized,
            'original': name,
            'style': 'first_last'
        }

    def are_names_similar(self, name1_str, name2_str, name1_style='auto', name2_style='auto'):
        name1 = self.parse_name_by_style(name1_str, name1_style)
        name2 = self.parse_name_by_style(name2_str, name2_style)

        if not name1['last'] or not name2['last']:
            is_match = name1['normalized'] == name2['normalized']
            return is_match, 1.0 if is_match else 0.0

        last_similarity = jellyfish.jaro_winkler_similarity(
            name1['last'],
            name2['last']
        )

        if last_similarity < self.name_matching_threshold:
            return False, last_similarity

        if name1['first'] and name2['first']:
            if len(name1['first']) == 1 or len(name2['first']) == 1:
                if name1['first'][0] == name2['first'][0]:
                    return True, (last_similarity + 0.9) / 2
                else:
                    return False, last_similarity * 0.5
            else:
                first_similarity = jellyfish.jaro_winkler_similarity(
                    name1['first'],
                    name2['first']
                )
                if first_similarity >= self.name_matching_threshold:
                    avg_similarity = (last_similarity + first_similarity) / 2
                    return True, avg_similarity
                else:
                    return False, last_similarity * 0.5

        if not name1['first'] or not name2['first']:
            if last_similarity >= 0.95:
                return True, last_similarity

        return False, last_similarity

    def match_affiliation(self, input_affiliation, candidate_affiliation, threshold=0.8, use_embeddings=True):
        if not input_affiliation or not candidate_affiliation:
            return False, 0.0

        if use_embeddings and self.embedding_model is not None:
            try:
                is_match, similarity = self.embedding_model.match_affiliation(
                    input_affiliation,
                    candidate_affiliation,
                    threshold
                )
                return is_match, similarity
            except Exception as e:
                logging.warning(f"Embedding model failed, falling back to string matching: {e}")

        norm_input = self.normalize_text(input_affiliation)
        norm_candidate = self.normalize_text(candidate_affiliation)

        if norm_input in norm_candidate or norm_candidate in norm_input:
            return True, 1.0

        similarity = jellyfish.jaro_winkler_similarity(
            norm_input, norm_candidate)

        is_match = similarity >= threshold
        return is_match, similarity

    def parse_authors_list(self, authors_str, separator=';', name_style='auto'):
        if not authors_str:
            return []

        authors = []
        for author_str in authors_str.split(separator):
            author_str = author_str.strip()
            if author_str:
                parsed = self.parse_name_by_style(author_str, name_style)
                authors.append(parsed)

        return authors

    def find_best_author_match(self, input_author, candidate_authors, input_style='auto', candidate_style='auto'):
        best_match = None
        best_score = 0

        for candidate in candidate_authors:
            is_similar, score = self.are_names_similar(
                input_author, candidate,
                name1_style=input_style,
                name2_style=candidate_style
            )

            if is_similar and score > best_score:
                best_match = candidate
                best_score = score

        return best_match, best_score
