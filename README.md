# OpenAlex Works Matching and Funder Verification

Tool for matching grant and publication records to OpenAlex works with two modes:
1. Title-based matching: Searches for works by normalizing and matching publication titles
2. Author-affiliation matching: Searches for works by matching author names and institutional affiliations

## Table of Contents
- [Installation](#installation)
- [Usage](#usage)
  - [Command Line Arguments](#command-line-arguments)
- [How Title Matching Works](#how-title-matching-works)
- [How Author-Affiliation Matching Works](#how-author-affiliation-matching-works)
- [Configuration](#configuration)
  - [Title-Based Matching Configuration](#title-based-matching-configuration)
  - [Author-Affiliation Matching Configuration](#author-affiliation-matching-configuration)
  - [Field Mappings](#field-mappings)
- [Output](#output)
  - [Common Fields](#common-fields-both-modes)
  - [Title-Based Matching Fields](#title-based-matching-fields)
  - [Author-Affiliation Matching Fields](#author-affiliation-matching-fields)
  - [OpenAlex Metadata](#openalex-metadata-when-matched)
- [API Rate Limits](#api-rate-limits)
- [Examples](#examples)
  - [Example 1: Title-Based Matching](#example-1-title-based-matching)
  - [Example 2: Author-Affiliation Matching](#example-2-author-affiliation-matching)
- [Logging](#logging)

## Installation

```bash
pip install -r requirements.txt
```

Download NLTK stopwords (first time only):
```python
import nltk
nltk.download('stopwords')
```

## Usage

### Command Line Arguments

```bash
# Basic usage with configuration file
python main.py -c config.yaml

# Enable verbose logging for debugging
python main.py -c config.yaml --verbose

# Perform a dry run (process without writing output)
python main.py -c config.yaml --dry-run

# Combine options
python main.py -c configs/config_nwo.yaml --verbose --dry-run
```

### Arguments

- `-c, --config`: Path to the YAML configuration file (required)
- `-v, --verbose`: Enable DEBUG level logging for detailed output
- `--dry-run`: Process records without writing output file (useful for testing)

## How Title Matching Works

The title-based matching process begins by normalizing the input title to improve matching accuracy. When a title comes in as input, the matching first looks for and extracts any dates that might be embedded in the title text. For example, a title like "9 July 2019, Climate Change Report" becomes simply "Climate Change Report" with the date extracted and stored separately. The normalization then continues on to identifying and removing common title additions such as subtitles (appearing after colons or dashes), content in parentheses or brackets, report numbers, version indicators, and suffixes like "abstract" or "preprint". The text is then converted to lowercase, special characters are removed, and Unicode characters are transliterated to their ASCII equivalents. When aggressive matching is used, English stopwords can be filtered out as well.

Once the title is normalized, the system searches OpenAlex using a two-stage approach. First, it attempts an exact search using the cleaned title. If this doesn't yield results above the specified similarity threshold, it falls back to a fuzzy search that can handle minor variations in wording. When a publication year is provided, the search is refined by filtering to publications within a ±2 year window, which significantly improves match accuracy and reduces false positives. The similarity between titles is calculated using Levenshtein distance, which measures the minimum number of single-character edits required to change one string into another.

After potential matches are found, the system validates them through additional checks. If author information is available, it compares the last names of authors from the input with those in the OpenAlex record, requiring at least an 85% similarity match. Publication years are also validated when available, with a +/- two year tolerance. Only matches that exceed th similarity threshold (default 95%) are returned as valid matches.

## How Author-Affiliation Matching Works

The author-affiliation matching approach is designed for scenarios where you have author names and institutional affiliations but may not have publication titles. This method searches for all publications by specific authors and their institutions, making it useful for tracking research outputs from grants where the principal investigator and their institution are known.

The matching process follows an institution-first strategy to minimize false positives. When a search begins, the system first attempts to resolve the institutional affiliation to a specific organization. It starts by searching the OpenAlex institutions database for organizations matching the affiliation string. If no match is found with sufficient confidence, the system falls back to the ROR (Research Organization Registry) API, which specializes in disambiguating messy affiliation strings to standardized institution identifiers. The ROR service can handle variations like "MIT" versus "Massachusetts Institute of Technology" or abbreviated forms like "U of T" for "University of Toronto."

Once an institution is identified, the system extracts the author's surname from the input name (handling various formats including "Last, First", "First Last", "Last Initial", and compound surnames like "De La Cruz"). It then searches specifically for authors with that surname who are affiliated with the identified institution.

When multiple authors are found at the institution, the system performs name disambiguation using the configured name matching style. Each name is normalized by converting Latin characters to ASCII equivalents and compared using Jaro-Winkler similarity scoring. The author with the highest name similarity score above the threshold is selected as the match. The system then retrieves publications where this author is specifically affiliated with the matched institution, filtering out any works from their time at other organizations. For example, if searching for "J Smith at MIT", the system will only return papers where J Smith lists MIT as their affiliation, excluding any papers from their previous position at Stanford or subsequent move to Harvard. This institution-specific filtering ensures clean, accurate results tied to the grant-awarding institution. Works are further filtered by year window if a grant year is provided.

When an author is successfully matched at an institution but has no publications there within the specified time window, the system returns an empty result rather than falling back to a broader search. This prevents false positives that could occur from matching similarly-named authors at other institutions. For instance, if "Mitchell G" at University of Strathclyde has no publications in 2013-2018, the system will correctly return no results rather than incorrectly matching to authors at other institutions.

If the institution cannot be resolved through either OpenAlex or ROR, the system falls back to a broader search strategy. In this fallback mode, it searches for authors by name across all institutions and then validates each potential match by comparing the affiliation strings. This comparison can use either fuzzy text matching or an embedding model (`cometadata/affiliation-clustering-0.3b`) specially trained on institution name disambiguation. The embedding model generates vector representations of institution names and uses cosine similarity to identify matches, allowing it to recognize that "Harvard Medical School" and "Harvard University" refer to related institutions even when the text differs significantly.

Each potential match is scored using a weighted combination of author name similarity (30% by default) and affiliation similarity (70% by default), reflecting the importance of institutional affiliation in reducing false positives. The matching requires a minimum affiliation score (85% by default) to consider a match valid. Unlike in the title-based matching, which produces one output row per input record, author-affiliation matching retunrs multiple output rows, one for each publication found for that author at that institution. Each output row includes the match scores for both author and affiliation, allowing the user to assess their confidence in each match.

## Configuration

The tool uses a YAML configuration file to specify input/output settings, field mappings, and API parameters.

### Title-Based Matching Configuration

```yaml
# Matching Mode
matching:
  mode: "title"

# Input Settings
input:
  path: "./data/grant_publications.csv"
  format: "csv"
  
  # Field mappings for title matching
  mappings:
    award_id: "grant_number"      # Required
    title: "publication_title"    # Required
    authors: "author_list"        # Optional (for validation)
    year: "pub_year"              # Optional (for filtering)

# Output Settings
output:
  path: "./output/enriched_publications.csv"
  format: "csv"

# API Settings
api:
  mailto: "name@email.com"       # Required for polite pool
  similarity_threshold: 95       # Title match threshold (0-100)
  
  target_funder_ids:
    - "https://openalex.org/F4320321800"

processing:
  limit: 100
  log_level: "INFO"
```

### Author-Affiliation Matching Configuration

```yaml
# Matching Mode
matching:
  mode: "author_affiliation"      
  
  # Author name parsing
  author_name_style: "last_comma_first"  # Format of input names
  author_separator: ";"           # Separator for multiple authors
  
  # Matching thresholds
  name_matching_threshold: 0.85   # Author name similarity (0-1)
  affiliation_matching_threshold: 0.8  # Affiliation similarity (0-1)
  
  # Scoring weights (should sum to 1.0)
  author_weight: 0.3              # Weight for author name matching (30%)
  affiliation_weight: 0.7         # Weight for affiliation matching (70%)
  
  # Minimum score requirements
  minimum_affiliation_score: 0.85  # Min affiliation score for fallback search
  
  # Institution search settings
  use_institution_search: true     # Use institution-first search strategy
  use_ror_api: true               # Use ROR API for institution resolution
  
  # Embedding model for semantic affiliation matching
  use_embedding_model: true
  embedding_model_path: "cometadata/affiliation-clustering-0.3b"
  embedding_similarity_threshold: 0.65  # Lower to catch abbreviations
  
  # Search settings
  max_results_per_author: 100     # Max publications per author
  year_search_window: 5            # Years forward from grant year

# Input Settings
input:
  path: "./data/grants_with_authors.csv"
  format: "csv"
  
  # Field mappings for author-affiliation matching
  mappings:
    award_id: "grant_id"          # Required
    authors: "pi_name"            # Required
    affiliation: "institution"    # Required
    year: "grant_year"            # Optional (for filtering)

# Output Settings
output:
  path: "./output/author_affiliation_matches.csv"
  format: "csv"

# API Settings
api:
  mailto: "name@email.com"
  
  target_funder_ids:
    - "https://openalex.org/F4320334593"
  
  error_tracking:
    max_error_rate: 0.8
    window_seconds: 300
    min_attempts: 10
    max_consecutive_failures: 5

processing:
  limit: 100
  log_level: "INFO"
```


### Field Mappings

The `mappings` section maps your input fields to standard fields. Required fields vary by matching mode:

#### Title-Based Matching Fields
| Standard Field | Description | Required | Example Mapping |
|---------------|-------------|----------|-----------------|
| `award_id` | Grant/award identifier | Yes | `"grant_number"` |
| `title` | Publication title | Yes | `"publication_title"` |
| `authors` | Author names | No | `"author_list"` |
| `year` | Publication year | No | `"pub_year"` |

#### Author-Affiliation Matching Fields
| Standard Field | Description | Required | Example Mapping |
|---------------|-------------|----------|-----------------|
| `award_id` | Grant/award identifier | Yes | `"grant_number"` |
| `authors` | Author/PI names | Yes | `"pi_name"` |
| `affiliation` | Institution name | Yes | `"institution"` |
| `year` | Grant/award year | No | `"grant_year"` |

For nested JSON fields, use dot notation:
```yaml
mappings:
  award_id: "grant.identifier"
  title: "publication.title"
  authors: "publication.authors"
  year: "publication.year"
```

## Output

The output includes all input records enriched with OpenAlex metadata. Output fields vary by matching mode:

### Common Fields (Both Modes)
- `match_status`: "matched", "no_match", or "failed"
- `match_method`: "title" or "author_affiliation"
- `metadata_source`: "openalex", "not_found", or error type

### Title-Based Matching Fields
```
# Matching Metadata
match_ratio              # Title similarity score (0-100)
search_method            # "exact" or "fuzzy"
cleaned_title            # Normalized title used for search
extracted_date           # Date extracted from title
matched_title            # Actual title from OpenAlex

# Validation Results
matched_authors          # Boolean: authors validated
matched_authors_count    # Number of matched authors
matched_authors_list     # Names of matched authors
year_match               # Boolean: year validated
year_difference          # Years between input and publication
```

### Author-Affiliation Matching Fields
```
# Matching Metadata
matched_author           # Matched author name from OpenAlex
matched_author_id        # OpenAlex author ID
matched_author_orcid     # ORCID if available
matched_affiliation      # Matched institution name
matched_affiliation_id   # OpenAlex institution ID
matched_affiliation_ror  # ROR ID if available
author_match_score       # Author name similarity (0-1)
affiliation_match_score  # Institution similarity (0-1)
combined_match_score     # Combined score for ranking

# Validation Results
year_match               # Boolean: publication within window
year_difference          # Years from grant to publication
```

### OpenAlex Metadata (When Matched)
```
# Core Metadata
openalex_work_id         # OpenAlex work ID
doi                      # Digital Object Identifier
publication_date         # Full publication date
publication_year         # Year only
type                     # Publication type
language                 # Language code
cited_by_count           # Citation count
is_retracted             # Retraction status

# Venue Information
journal                  # Journal/venue name
issn                     # ISSN
publisher                # Publisher name
volume                   # Journal volume
issue                    # Journal issue
pages                    # Page numbers

# Open Access
is_oa                    # Open access status
oa_status                # OA type (gold, green, bronze, closed)
oa_url                   # Open access URL
best_oa_landing_page_url # Best OA landing page
best_oa_pdf_url          # Direct PDF link
best_oa_license          # License type
best_oa_version          # Manuscript version

# Content
authors/work_authors     # Complete author list
authors_count            # Number of authors
topics                   # Research topics/concepts
abstract                 # Work abstract (if available)

# Funding Information
has_any_target_funder    # Any target funder found
has_target_funder        # Specific target funder found
matched_target_funders   # List of matched funder IDs
matched_target_funder_names # Funder names
target_funder_match_count # Number of matched funders
funding_info             # All funding information
funding_count            # Total number of funders
award_id_match           # Award ID found
matched_grant_award_id   # Matched award ID
matched_grant_funder     # Funder for matched award
```

## API Rate Limits

Respects OpenAlex API limits:
- With email: (polite pool): 10 requests/second
- Without email: 1 request/second (not recommended)

## Examples

### Example 1: Title-Based Matching
```bash
# Search for publications by title
python main.py -c samples/sample_config/config_ukri.yaml

# With verbose logging
python main.py -c samples/sample_config/config_ukri.yaml --verbose

# Dry run to test configuration
python main.py -c samples/sample_config/config_ukri.yaml --dry-run
```

Sample input (CSV):
```csv
grant_number,publication_title,author_list,pub_year
ABC123,"Machine Learning for Climate Prediction","Smith J; Jones A",2023
DEF456,"Novel Approaches to Quantum Computing","Brown M; Lee K",2022
```

Sample output: One row per input record with matched OpenAlex metadata.

### Example 2: Author-Affiliation Matching
```bash
# Search for publications by author and institution
python main.py -c samples/sample_config/config_nserc_author_affiliation.yaml

# Process first 10 records only
python main.py -c samples/sample_config/config_nserc_author_affiliation.yaml
```

Sample input (CSV):
```csv
ApplicationID,Name-Nom,Institution-Établissement,FiscalYear
12345,"Smith, John",University of Toronto,2020
67890,"Jones, Alice",McGill University,2021
```

Sample output: Multiple rows per grant (one per matched publication) with author/affiliation match scores.


## Logging
- Log file: `matching_YYYYMMDD_HHMMSS.log`
- Console output shows progress every 10 records
- Use `--verbose` flag for detailed debugging info