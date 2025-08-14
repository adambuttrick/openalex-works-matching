import os
import csv
import json
import logging
from abc import ABC, abstractmethod


def get_nested_value(data, path):
    if not path or path == '.':
        return data
    
    keys = path.split('.')
    value = data
    
    for key in keys:
        if isinstance(value, dict):
            value = value.get(key)
        elif isinstance(value, list) and key.isdigit():
            idx = int(key)
            if 0 <= idx < len(value):
                value = value[idx]
            else:
                return None
        else:
            return None
        
        if value is None:
            return None
    
    return value


def extract_authors_from_nested(data):
    authors = []
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                name = item.get('last_name', '')
                if not name:
                    name = item.get('name', '')
                if not name:
                    name = item.get('display_name', '')
                if name:
                    first = item.get('first_name', '')
                    if not first:
                        first = item.get('initials', '')
                    if first:
                        name = f"{name}, {first}"
                    authors.append(name)
            elif isinstance(item, str):
                authors.append(item)
    elif isinstance(data, str):
        return data
    
    return '; '.join(authors) if authors else None


class DataReader(ABC):
    """Abstract base class for data readers."""
    
    def __init__(self, file_path, field_mappings):
        self.file_path = file_path
        self.field_mappings = field_mappings
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Input file not found: {file_path}")
    
    @abstractmethod
    def read_records(self):
        pass
    
    def map_record(self, raw_record):
        mapped_record = {}
        
        for standard_field, source_path in self.field_mappings.items():
            value = get_nested_value(raw_record, source_path)
            
            if standard_field == 'authors' and value is not None:
                value = extract_authors_from_nested(value)
            
            mapped_record[standard_field] = value
        
        return mapped_record


class CSVReader(DataReader):
    def read_records(self):
        with open(self.file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                yield self.map_record(row)


class JSONReader(DataReader):
    def __init__(self, file_path, field_mappings,
                 records_path='.'):
        super().__init__(file_path, field_mappings)
        self.records_path = records_path
    
    def read_records(self):
        with open(self.file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        records = get_nested_value(data, self.records_path)
        
        if not isinstance(records, list):
            if isinstance(records, dict):
                records = [records]
            else:
                logging.warning(f"No records found at path: {self.records_path}")
                return
        
        for record in records:
            products = record.get('products', [])
            if products:
                for product in products:
                    combined_record = {
                        'project_id': record.get('project_id'),
                        'project_title': record.get('title'),
                        **product
                    }
                    yield self.map_record(combined_record)
            else:
                yield self.map_record(record)


class DataWriter(ABC):
    def __init__(self, file_path):
        self.file_path = file_path
        self.first_record_written = False
        
        output_dir = os.path.dirname(file_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
    
    @abstractmethod
    def write_header(self, fields):
        pass
    
    @abstractmethod
    def write_record(self, record):
        pass
    
    @abstractmethod
    def finalize(self):
        pass


class CSVWriter(DataWriter):
    def __init__(self, file_path):
        super().__init__(file_path)
        self.file = open(file_path, 'w', encoding='utf-8')
        self.writer = None
        self.fieldnames = None
    
    def write_header(self, fields):
        self.fieldnames = fields
        self.writer = csv.DictWriter(self.file, fieldnames=fields)
        self.writer.writeheader()
    
    def write_record(self, record):
        if not self.writer:
            self.write_header(list(record.keys()))
        
        row = {field: record.get(field, '') for field in self.fieldnames}
        
        for key, value in row.items():
            if isinstance(value, list):
                row[key] = '; '.join(str(v) for v in value)
            elif value is None:
                row[key] = ''
        
        self.writer.writerow(row)
        self.file.flush()
    
    def finalize(self):
        self.file.close()


class JSONWriter(DataWriter):
    def __init__(self, file_path):
        super().__init__(file_path)
        self.records = []
    
    def write_header(self, fields):
        pass
    
    def write_record(self, record):
        cleaned_record = {}
        for key, value in record.items():
            if value is None:
                cleaned_record[key] = ''
            else:
                cleaned_record[key] = value
        
        self.records.append(cleaned_record)
    
    def finalize(self):
        with open(self.file_path, 'w', encoding='utf-8') as f:
            json.dump(self.records, f, indent=2, ensure_ascii=False)


def create_reader(file_path, format, field_mappings,
                  records_path=None):
    if format.lower() == 'csv':
        return CSVReader(file_path, field_mappings)
    elif format.lower() == 'json':
        return JSONReader(file_path, field_mappings, records_path or '.')
    else:
        raise ValueError(f"Unsupported input format: {format}")


def create_writer(file_path, format):
    if format.lower() == 'csv':
        return CSVWriter(file_path)
    elif format.lower() == 'json':
        return JSONWriter(file_path)
    else:
        raise ValueError(f"Unsupported output format: {format}")