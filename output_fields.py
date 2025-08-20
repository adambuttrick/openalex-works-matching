INPUT_FIELDS = [
    'award_id',
    'title',
    'url',
    'year',
    'authors',
    'affiliation'
]

MATCHING_FIELDS = [
    'match_status',
    'match_method',
    # Title-specific matching fields
    'match_ratio',
    'search_method',
    'extracted_doi',
    'cleaned_title',
    'extracted_date',
    'date_format',
    'matched_title',
    # Author-affiliation specific matching fields
    'matched_author',
    'matched_author_id',
    'matched_author_orcid',
    'matched_affiliation',
    'matched_affiliation_id',
    'matched_affiliation_ror',
    'author_match_score',
    'affiliation_match_score',
    'combined_match_score',
]

OPENALEX_FIELDS = [
    'openalex_work_id',
    'metadata_source',
    'publication_year',
    'publication_date',
    'doi',
    'type',
    'language',
    'cited_by_count',
    'is_retracted',
    'work_authors',
    'authors_count',
    'journal',
    'issn',
    'publisher',
    'volume',
    'issue',
    'pages',
    'oa_status',
    'is_oa',
    'oa_url',
    'best_oa_landing_page_url',
    'best_oa_pdf_url',
    'best_oa_license',
    'best_oa_version',
    'topics',
    'abstract',
]

FUNDING_FIELDS = [
    'has_any_target_funder',
    'has_target_funder',
    'matched_target_funders',
    'matched_target_funder_names',
    'target_funder_match_count',
    'funding_info',
    'funding_count',
    'award_id_match',
    'award_id_match_type',
    'award_id_match_score',
    'matched_grant_award_id',
    'matched_grant_funder',
]

VALIDATION_FIELDS = [
    'matched_authors',
    'matched_authors_count',
    'matched_authors_list',
    'year_match',
    'year_difference',
]

ALL_OUTPUT_FIELDS = (
    INPUT_FIELDS + 
    MATCHING_FIELDS + 
    OPENALEX_FIELDS + 
    FUNDING_FIELDS + 
    VALIDATION_FIELDS
)

def get_output_fields_for_mode(matching_mode='title'):
    if matching_mode == 'author_affiliation':
        exclude = {'title', 'url', 'cleaned_title', 'extracted_date', 'date_format', 
                   'matched_title', 'match_ratio', 'search_method', 'extracted_doi',
                   'matched_authors', 'matched_authors_count', 'matched_authors_list'}
        return [f for f in ALL_OUTPUT_FIELDS if f not in exclude]
    else:
        exclude = {'affiliation', 'matched_author', 'matched_author_id', 'matched_author_orcid',
                   'matched_affiliation', 'matched_affiliation_id', 'matched_affiliation_ror',
                   'author_match_score', 'affiliation_match_score', 'combined_match_score',
                   'work_authors'}
        return [f for f in ALL_OUTPUT_FIELDS if f not in exclude]