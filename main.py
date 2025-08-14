import sys
import time
import logging
import argparse
from pathlib import Path
from datetime import datetime

from config import ConfigLoader, ConfigurationError
from data_io import create_reader, create_writer
from openalex_client import OpenAlexClient, APIHealthError
from processing import ProcessingEngine


def setup_logging(log_level):
    level = getattr(logging, log_level.upper(), logging.INFO)
    
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    log_file = f"matching_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)
    logging.getLogger().addHandler(file_handler)
    
    logging.info(f"Logging initialized at {log_level} level. Log file: {log_file}")


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="OpenAlex works matching "
                    "Match publications from basic metadata using the OpenAlex API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Example usage:
  python main.py config.yaml
  python main.py --verbose config.yaml
  python main.py --dry-run config.yaml
"""
    )
    
    parser.add_argument(
        '-c', '--config',
        help='Path to the YAML configuration file'
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose (DEBUG) logging'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Perform a dry run (process but do not write output)'
    )
    
    return parser.parse_args()


def print_summary(stats):
    print("\n" + "="*60)
    print("PROCESSING SUMMARY")
    print("="*60)
    print(f"Total records processed: {stats['total_processed']}")
    print(f"Successfully matched: {stats['matched']} ({stats['match_rate']:.1f}%)")
    print(f"No match found: {stats['no_match']}")
    print(f"Errors: {stats['errors']}")
    
    if stats['matched'] > 0:
        print(f"\nAverage match ratio: {stats['avg_match_ratio']:.1f}%")
    
    print(f"\nProcessing time: {stats['processing_time']:.2f} seconds")
    print(f"Average time per record: {stats['avg_time_per_record']:.2f} seconds")
    
    if stats.get('api_stats'):
        print(f"\nOpenAlex API stats: {stats['api_stats']}")
    
    print("="*60 + "\n")


def main():
    args = parse_arguments()
    
    try:
        print(f"Loading configuration from: {args.config}")
        config = ConfigLoader(args.config)
        
        log_level = 'DEBUG' if args.verbose else config.get_log_level()
        setup_logging(log_level)
        
        logging.info(f"Input: {config.get_input_path()} (format: {config.get_input_format()})")
        logging.info(f"Output: {config.get_output_path()} (format: {config.get_output_format()})")
        logging.info(f"Similarity threshold: {config.get_similarity_threshold()}%")
        
        logging.info("Initializing OpenAlex client...")
        openalex_client = OpenAlexClient(
            mailto=config.get_mailto(),
            similarity_threshold=config.get_similarity_threshold(),
            error_tracking_config=config.get_error_tracking_config()
        )
        
        processing_engine = ProcessingEngine(config, openalex_client)
        
        reader = create_reader(
            file_path=config.get_input_path(),
            format=config.get_input_format(),
            field_mappings=config.get_field_mappings(),
            records_path=config.get_records_path()
        )
        
        writer = None
        if not args.dry_run:
            writer = create_writer(
                file_path=config.get_output_path(),
                format=config.get_output_format()
            )
        
        stats = {
            'total_processed': 0,
            'matched': 0,
            'no_match': 0,
            'errors': 0,
            'match_ratios': [],
            'start_time': time.time()
        }
        
        limit = config.get_processing_limit()
        
        print(f"\nStarting processing...")
        if limit:
            print(f"Processing limit: {limit} records")
        
        try:
            for i, record in enumerate(reader.read_records(), 1):
                if limit and i > limit:
                    logging.info(f"Reached processing limit of {limit} records")
                    break
                
                try:
                    logging.info(f"Processing record {i}: {record.get('award_id', 'unknown')}")
                    enriched_record = processing_engine.process_record(record)
                    
                    stats['total_processed'] += 1
                    
                    if enriched_record.get('match_status') == 'matched':
                        stats['matched'] += 1
                        match_ratio = enriched_record.get('match_ratio', 0)
                        stats['match_ratios'].append(match_ratio)
                    elif enriched_record.get('match_status') == 'no_match':
                        stats['no_match'] += 1
                    
                    if writer:
                        writer.write_record(enriched_record)
                    
                    if i % 10 == 0:
                        print(f"Processed {i} records... ({stats['matched']} matched)")
                    
                except APIHealthError as e:
                    logging.error(f"API health check failed: {e}")
                    print(f"\nERROR: {e}")
                    print("Stopping processing due to API issues.")
                    break
                    
                except Exception as e:
                    logging.error(f"Error processing record {i}: {e}", exc_info=True)
                    stats['errors'] += 1
                    
                    error_record = dict(record)
                    error_record['error'] = str(e)
                    error_record['match_status'] = 'error'
                    
                    if writer:
                        writer.write_record(error_record)
        
        finally:
            if writer:
                writer.finalize()
        
        stats['end_time'] = time.time()
        stats['processing_time'] = stats['end_time'] - stats['start_time']
        
        if stats['total_processed'] > 0:
            stats['match_rate'] = (stats['matched'] / stats['total_processed']) * 100
            stats['avg_time_per_record'] = stats['processing_time'] / stats['total_processed']
        else:
            stats['match_rate'] = 0
            stats['avg_time_per_record'] = 0
        
        if stats['match_ratios']:
            stats['avg_match_ratio'] = sum(stats['match_ratios']) / len(stats['match_ratios'])
        else:
            stats['avg_match_ratio'] = 0
        
        stats['api_stats'] = openalex_client.error_tracker.get_stats()
        
        print_summary(stats)
        
        if not args.dry_run:
            print(f"Output written to: {config.get_output_path()}")
        else:
            print("Dry run completed - no output written")
        
        return 0
        
    except ConfigurationError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 1
        
    except FileNotFoundError as e:
        print(f"File not found: {e}", file=sys.stderr)
        return 1
        
    except KeyboardInterrupt:
        print("\nProcessing interrupted by user")
        return 130
        
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        logging.error("Unexpected error", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())