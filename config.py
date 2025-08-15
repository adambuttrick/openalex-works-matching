import os
import yaml


class ConfigurationError(Exception):
    pass


class ConfigLoader:
    def __init__(self, config_path):
        self.config_path = config_path
        self.config = self._load_config()
        self.validate()
    
    def _load_config(self):
        if not os.path.exists(self.config_path):
            raise ConfigurationError(f"Configuration file not found: {self.config_path}")
        
        try:
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f)
            if config is None:
                raise ConfigurationError("Configuration file is empty")
            return config
        except yaml.YAMLError as e:
            raise ConfigurationError(f"Error parsing YAML configuration: {e}")
        except Exception as e:
            raise ConfigurationError(f"Error loading configuration: {e}")
    
    def validate(self):
        required_sections = ['input', 'output', 'api']
        for section in required_sections:
            if section not in self.config:
                raise ConfigurationError(f"Missing required section: {section}")
        
        input_config = self.config['input']
        if 'path' not in input_config:
            raise ConfigurationError("Missing required field: input.path")
        if 'format' not in input_config:
            raise ConfigurationError("Missing required field: input.format")
        if input_config['format'] not in ['csv', 'json']:
            raise ConfigurationError(f"Invalid input format: {input_config['format']}. Must be 'csv' or 'json'")
        if 'mappings' not in input_config:
            raise ConfigurationError("Missing required field: input.mappings")
        
        matching_mode = self.config.get('matching', {}).get('mode', 'title')
        
        mappings = input_config['mappings']
        
        if matching_mode == 'author_affiliation':
            required_mappings = ['award_id', 'authors', 'affiliation']
            for mapping in required_mappings:
                if mapping not in mappings:
                    raise ConfigurationError(f"Missing required mapping for author-affiliation mode: input.mappings.{mapping}")
        else:
            required_mappings = ['award_id', 'title']
            for mapping in required_mappings:
                if mapping not in mappings:
                    raise ConfigurationError(f"Missing required mapping: input.mappings.{mapping}")
        
        output_config = self.config['output']
        if 'path' not in output_config:
            raise ConfigurationError("Missing required field: output.path")
        if 'format' not in output_config:
            raise ConfigurationError("Missing required field: output.format")
        if output_config['format'] not in ['csv', 'json']:
            raise ConfigurationError(f"Invalid output format: {output_config['format']}. Must be 'csv' or 'json'")
        
        api_config = self.config['api']
        if 'mailto' not in api_config:
            raise ConfigurationError("Missing required field: api.mailto (required for OpenAlex polite pool)")
        
        if 'similarity_threshold' in api_config:
            threshold = api_config['similarity_threshold']
            if not isinstance(threshold, (int, float)) or threshold < 0 or threshold > 100:
                raise ConfigurationError("api.similarity_threshold must be a number between 0 and 100")
        
        if 'error_tracking' in api_config:
            error_config = api_config['error_tracking']
            if 'max_error_rate' in error_config:
                rate = error_config['max_error_rate']
                if not isinstance(rate, (int, float)) or rate < 0 or rate > 1:
                    raise ConfigurationError("api.error_tracking.max_error_rate must be between 0.0 and 1.0")
    
    @property
    def input_settings(self):
        return self.config['input']
    
    @property
    def output_settings(self):
        return self.config['output']
    
    @property
    def api_settings(self):
        return self.config['api']
    
    @property
    def processing_settings(self):
        return self.config.get('processing', {})
    
    def get_input_path(self):
        return self.input_settings['path']
    
    def get_output_path(self):
        return self.output_settings['path']
    
    def get_input_format(self):
        return self.input_settings['format']
    
    def get_output_format(self):
        return self.output_settings['format']
    
    def get_field_mappings(self):
        return self.input_settings['mappings']
    
    def get_records_path(self):
        return self.input_settings.get('records_path', '.')
    
    def get_mailto(self):
        return self.api_settings['mailto']
    
    def get_similarity_threshold(self):
        return self.api_settings.get('similarity_threshold', 95)
    
    def get_error_tracking_config(self):
        default_config = {
            'max_error_rate': 0.8,
            'window_seconds': 300,
            'min_attempts': 10,
            'max_consecutive_failures': 5
        }
        error_config = self.api_settings.get('error_tracking', {})
        default_config.update(error_config)
        return default_config
    
    def get_processing_limit(self):
        return self.processing_settings.get('limit', None)
    
    def get_log_level(self):
        return self.processing_settings.get('log_level', 'INFO')
    
    def get_target_funder_ids(self):
        if 'target_funder_ids' in self.api_settings:
            funder_ids = self.api_settings['target_funder_ids']
            if isinstance(funder_ids, str):
                return [funder_ids]
            elif isinstance(funder_ids, list):
                return funder_ids
            else:
                return None
        
        elif 'target_funder_id' in self.api_settings:
            funder_id = self.api_settings['target_funder_id']
            if funder_id:
                return [funder_id]
        
        return None
    
    @property
    def matching_settings(self):
        return self.config.get('matching', {})
    
    def get_matching_mode(self):
        return self.matching_settings.get('mode', 'title')
    
    def get_author_name_style(self):
        return self.matching_settings.get('author_name_style', 'auto')
    
    def get_author_separator(self):
        return self.matching_settings.get('author_separator', ';')
    
    def get_name_matching_threshold(self):
        threshold = self.matching_settings.get('name_matching_threshold', 0.85)
        if not isinstance(threshold, (int, float)) or threshold < 0 or threshold > 1:
            raise ConfigurationError("matching.name_matching_threshold must be between 0.0 and 1.0")
        return threshold
    
    def get_affiliation_matching_threshold(self):
        threshold = self.matching_settings.get('affiliation_matching_threshold', 0.8)
        if not isinstance(threshold, (int, float)) or threshold < 0 or threshold > 1:
            raise ConfigurationError("matching.affiliation_matching_threshold must be between 0.0 and 1.0")
        return threshold
    
    def use_embedding_model(self):
        return self.matching_settings.get('use_embedding_model', True)
    
    def get_embedding_model_path(self):
        return self.matching_settings.get('embedding_model_path', 'cometadata/affiliation-clustering-0.3b')
    
    def get_embedding_similarity_threshold(self):
        threshold = self.matching_settings.get('embedding_similarity_threshold', 0.7)
        if not isinstance(threshold, (int, float)) or threshold < 0 or threshold > 1:
            raise ConfigurationError("matching.embedding_similarity_threshold must be between 0.0 and 1.0")
        return threshold
    
    def get_max_results_per_author(self):
        return self.matching_settings.get('max_results_per_author', 50)
    
    def get_year_search_window(self):
        return self.matching_settings.get('year_search_window', None)