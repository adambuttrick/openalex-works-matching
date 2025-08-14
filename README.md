# OpenAlex Works Matching and Funder Verification

Tool for matching unstructured works references from sources funder grant databases to corresponding works records in OpenAlex, verifying whether specified funders and awards are associated with those works.

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

## Configuration

The tool uses a YAML configuration file to specify input/output settings, field mappings, and API parameters.

### Configuration Example

```yaml
# Input Settings
input:
  # Path to input file containing grant/publication records
  path: "./data/grant_publications.csv"
  
  # Format: 'csv' or 'json'
  format: "csv"
  
  # For JSON: path to records array (use "." for root array)
  # Examples: ".", "projects", "data.records"
  records_path: "projects"
  
  # Field mappings from your data to standard fields
  mappings:
    # Required: grant/award identifier
    award_id: "grant_number"
    
    # Required: publication title
    title: "publication_title"
    
    # Optional: author names (string or array)
    authors: "author_list"
    
    # Optional: publication year
    year: "pub_year"

# Output Settings
output:
  # Path for enriched output file
  path: "./output/enriched_publications.csv"
  
  # Format: 'csv' or 'json'
  format: "csv"

# API & Matching Settings
api:
  # REQUIRED: Your email for OpenAlex polite pool (10 req/sec)
  mailto: "name@email.com"
  
  # Title similarity threshold (0-100, default: 95)
  # Higher = stricter matching
  similarity_threshold: 95
  
  # Target funder IDs to verify in matched works
  # Can be single ID or list of IDs
  target_funder_ids:
    - "https://openalex.org/F4320321800"
    - "https://openalex.org/F4320306076"
    - "https://openalex.org/F4320306101"
  
  # Error tracking and health monitoring
  error_tracking:
    max_error_rate: 0.8          # Stop if error rate exceeds 80%
    window_seconds: 300           # Track errors over 5 minutes
    min_attempts: 10              # Min requests before health check
    max_consecutive_failures: 5   # Stop after 5 consecutive failures

# Processing Settings
processing:
  # Limit records for testing (remove for production)
  limit: 100
  
  # Logging level: DEBUG, INFO, WARNING, ERROR
  log_level: "INFO"
```


### Field Mappings

The `mappings` section maps your input fields to a standard set of fields used by the utiltiy:

| Standard Field | Description | Required | Example Mapping |
|---------------|-------------|----------|-----------------|
| `award_id` | Grant/award identifier | Yes | `"grant_number"` |
| `title` | Publication title | Yes | `"publication_title"` |
| `authors` | Author names | No | `"author_list"` |
| `year` | Publication year | No | `"pub_year"` |

For nested JSON fields, use dot notation:
```yaml
mappings:
  award_id: "grant.identifier"
  title: "publication.title"
  authors: "publication.authors"
  year: "publication.year"
```

## Output

The output include the input records with metadata from OpenAlex:

- All original input fields
- `match_status`: "matched", "no_match", or "error"
- `match_ratio`: Similarity score (0-100)
- `search_method`: "exact" or "fuzzy"
- `cleaned_title`: Normalized title used for search

### OpenAlex Metadata (When Matched)
```csv
openalex_id          # OpenAlex work ID
doi                  # Digital Object Identifier
publication_date     # Full publication date
publication_year     # Year only
title                # Official title from OpenAlex
journal              # Journal/venue name
publisher            # Publisher name
volume               # Journal volume
issue                # Journal issue
pages                # Page numbers
is_oa                # Open access status
oa_url               # Open access URL if available
authors              # Complete author list
author_institutions  # Author affiliations
abstract             # Work abstract
cited_by_count       # Citation count
references_count     # Reference count
concepts             # Research concepts/topics
funders              # All funders
funder_award_ids     # All award IDs
target_funder_found  # Whether funder was found
target_award_found   # Whether award ID was found
```

### Validation Results
```csv
matched_authors         # Boolean: authors validated
matched_authors_count   # Number of matched authors
matched_authors_list    # Names of matched authors
year_validation         # "valid", "invalid", or "missing"
year_difference         # Years between input and date of publication
```

## API Rate Limits

Respects OpenAlex API limits:
- With email: (polite pool): 10 requests/second
- Without email: 1 request/second (not recommended)

## Logging
- Log file: `matching_YYYYMMDD_HHMMSS.log`
- Console output shows progress every 10 records
- Use `--verbose` flag for detailed debugging info