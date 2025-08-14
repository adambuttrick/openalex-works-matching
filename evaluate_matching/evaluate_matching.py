import sys
import json
import argparse
from pathlib import Path
import pandas as pd
import numpy as np


def load_data(benchmark_file, results_file, id_column=None, title_column=None, openalex_column=None):
    print("Loading data files...")
    
    benchmark = pd.read_csv(benchmark_file)
    print(f"Loaded benchmark: {len(benchmark)} rows")
    
    results = pd.read_csv(results_file)
    print(f"Loaded results: {len(results)} rows")
    
    column_mapping = {}
    
    if id_column is None:
        id_candidates = ['project_id', 'award_id', 'grant_id', 'id']
        for col in id_candidates:
            if col in benchmark.columns and col in results.columns:
                id_column = col
                break
        if id_column is None:
            common_cols = set(benchmark.columns) & set(results.columns)
            id_like_cols = [c for c in common_cols if 'id' in c.lower()]
            if id_like_cols:
                id_column = id_like_cols[0]
    
    if id_column is None:
        raise ValueError("Could not auto-detect ID column. Please specify with --id-column")
    column_mapping['id'] = id_column
    
    if title_column is None:
        title_candidates = ['product_title', 'title', 'publication_title', 'paper_title']
        for col in title_candidates:
            if col in benchmark.columns and col in results.columns:
                title_column = col
                break
        if title_column is None:
            common_cols = set(benchmark.columns) & set(results.columns)
            title_like_cols = [c for c in common_cols if 'title' in c.lower()]
            if title_like_cols:
                title_column = title_like_cols[0]
    
    if title_column is None:
        raise ValueError("Could not auto-detect title column. Please specify with --title-column")
    column_mapping['title'] = title_column
    
    if openalex_column is None:
        openalex_column = 'openalex_work_id'
    column_mapping['openalex'] = openalex_column
    
    if id_column not in benchmark.columns:
        raise ValueError(f"ID column '{id_column}' not found in benchmark file")
    if id_column not in results.columns:
        raise ValueError(f"ID column '{id_column}' not found in results file")
    if title_column not in benchmark.columns:
        raise ValueError(f"Title column '{title_column}' not found in benchmark file")
    if title_column not in results.columns:
        raise ValueError(f"Title column '{title_column}' not found in results file")
    if openalex_column not in benchmark.columns:
        raise ValueError(f"OpenAlex column '{openalex_column}' not found in benchmark file")
    if openalex_column not in results.columns:
        raise ValueError(f"OpenAlex column '{openalex_column}' not found in results file")
    
    print(f"\nUsing columns:")
    print(f"  ID column: {id_column}")
    print(f"  Title column: {title_column}")
    print(f"  OpenAlex column: {openalex_column}")
    
    benchmark['unique_id'] = benchmark[id_column].astype(str) + '|||' + benchmark[title_column].astype(str)
    results['unique_id'] = results[id_column].astype(str) + '|||' + results[title_column].astype(str)
    
    return benchmark, results, column_mapping


def calculate_confusion_matrix(benchmark, results, openalex_column, mode='full'):
    print(f"\nCalculating confusion matrix ({mode} mode)...")
    
    join_type = 'inner' if mode == 'overlap' else 'outer'
    
    merged = pd.merge(
        benchmark[['unique_id', openalex_column]],
        results[['unique_id', openalex_column]],
        on='unique_id',
        how=join_type,
        suffixes=('_benchmark', '_results')
    )
    
    if mode == 'overlap':
        print(f"Evaluating {len(merged)} products present in both datasets")
    else:
        print(f"Evaluating {len(merged)} total unique products")
    
    tp = 0
    fp = 0
    fn = 0
    tn = 0
    
    for _, row in merged.iterrows():
        benchmark_id = row[f'{openalex_column}_benchmark']
        results_id = row[f'{openalex_column}_results']
        
        if pd.notna(benchmark_id) and pd.notna(results_id):
            if benchmark_id == results_id:
                tp += 1
            else:
                fp += 1
        elif pd.notna(benchmark_id) and pd.isna(results_id):
            fn += 1
        elif pd.isna(benchmark_id) and pd.notna(results_id):
            fp += 1
        else:
            tn += 1
    
    result = {
        'tp': tp,
        'fp': fp,
        'fn': fn,
        'tn': tn,
        'total': len(merged)
    }
    
    if mode == 'overlap':
        result['overlap_count'] = len(merged)
    
    return result


def calculate_metrics(confusion):
    tp = confusion['tp']
    fp = confusion['fp']
    fn = confusion['fn']
    tn = confusion['tn']
    
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    accuracy = (tp + tn) / confusion['total'] if confusion['total'] > 0 else 0.0
    
    def f_beta_score(precision, recall, beta):
        if precision + recall == 0:
            return 0.0
        beta_squared = beta ** 2
        return (1 + beta_squared) * (precision * recall) / (beta_squared * precision + recall)
    
    f05 = f_beta_score(precision, recall, 0.5)
    f1 = f_beta_score(precision, recall, 1.0)
    f15 = f_beta_score(precision, recall, 1.5)
    
    return {
        'precision': precision,
        'recall': recall,
        'f0.5': f05,
        'f1': f1,
        'f1.5': f15,
        'accuracy': accuracy
    }


def analyze_errors(benchmark, results, column_mapping, max_errors=100):
    id_col = column_mapping['id']
    title_col = column_mapping['title']
    openalex_col = column_mapping['openalex']
    
    merged = pd.merge(
        benchmark[['unique_id', id_col, title_col, openalex_col]],
        results[['unique_id', openalex_col]],
        on='unique_id',
        how='inner',
        suffixes=('_benchmark', '_results')
    )
    
    errors = []
    
    for _, row in merged.iterrows():
        benchmark_id = row[f'{openalex_col}_benchmark']
        results_id = row[f'{openalex_col}_results']
        
        error_type = None
        if pd.notna(benchmark_id) and pd.isna(results_id):
            error_type = 'False Negative'
        elif pd.isna(benchmark_id) and pd.notna(results_id):
            error_type = 'False Positive'
        elif pd.notna(benchmark_id) and pd.notna(results_id) and benchmark_id != results_id:
            error_type = 'False Positive'
        
        if error_type:
            errors.append({
                id_col: row[id_col],
                title_col: row[title_col][:100],
                'error_type': error_type,
                'benchmark_id': benchmark_id if pd.notna(benchmark_id) else 'None',
                'results_id': results_id if pd.notna(results_id) else 'None'
            })
            
            if len(errors) >= max_errors:
                break
    
    return pd.DataFrame(errors)


def generate_report(confusion, metrics, error_df, benchmark_file, results_file, 
                   mode='full', output_file=None):
    print("\n" + "="*60)
    print("MATCHING EVALUATION REPORT")
    print("="*60)
    print(f"\nMode: {mode.upper()}")
    print(f"Benchmark: {benchmark_file}")
    print(f"Results:   {results_file}")
    
    if 'overlap_count' in confusion:
        print(f"\nEvaluating {confusion['overlap_count']} products in overlap")
    
    print("\n1. CONFUSION MATRIX:")
    print(f"   True Positives (TP):  {confusion['tp']:>6}")
    print(f"   False Positives (FP): {confusion['fp']:>6}")
    print(f"   False Negatives (FN): {confusion['fn']:>6}")
    print(f"   True Negatives (TN):  {confusion['tn']:>6}")
    print(f"   Total Products:       {confusion['total']:>6}")
    
    print("\n2. EVALUATION METRICS:")
    print(f"   Precision:  {metrics['precision']:.4f}  (% of predicted matches that are correct)")
    print(f"   Recall:     {metrics['recall']:.4f}  (% of actual matches that were found)")
    print(f"   Accuracy:   {metrics['accuracy']:.4f}  (% of all predictions that are correct)")
    
    print("\n3. F-SCORES:")
    print(f"   F0.5 Score (Precision-weighted): {metrics['f0.5']:.4f}")
    print(f"   F1.0 Score (Balanced):          {metrics['f1']:.4f}")
    print(f"   F1.5 Score (Recall-weighted):   {metrics['f1.5']:.4f}")
    
    if output_file:
        report_data = {
            'configuration': {
                'benchmark_file': benchmark_file,
                'results_file': results_file,
                'mode': mode
            },
            'confusion_matrix': confusion,
            'metrics': metrics,
            'error_summary': error_df['error_type'].value_counts().to_dict() if len(error_df) > 0 else {}
        }
        
        with open(output_file, 'w') as f:
            json.dump(report_data, f, indent=2)
        print(f"\n6. DETAILED REPORT SAVED TO: {output_file}")
        
        if len(error_df) > 0:
            error_csv = output_file.replace('.json', '_errors.csv')
            error_df.to_csv(error_csv, index=False)
            print(f"   Error details saved to: {error_csv}")
    
    print("\n" + "="*60)


def main():
    parser = argparse.ArgumentParser(
        description='Benchmarking utility for matching performance.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Basic usage with auto-detection
  python evaluate_matching.py benchmark.csv results.csv
  
  # Specify custom columns
  python evaluate_matching.py benchmark.csv results.csv --id-column grant_id --title-column paper_title
  
  # Evaluate only overlapping products
  python evaluate_matching.py benchmark.csv results.csv --mode overlap
  
  # Save detailed report
  python evaluate_matching.py benchmark.csv results.csv --output report.json
        '''
    )
    
    parser.add_argument('-r', '--results', help='Path to results CSV file (predictions)')
    parser.add_argument('-b','--benchmark', help='Path to benchmark CSV file (ground truth)')
    
    parser.add_argument('--mode', choices=['full', 'overlap'], default='full',
                       help='Evaluation mode: "full" evaluates all products, "overlap" only evaluates products in both datasets (default: full)')
    parser.add_argument('--id-column', help='Column name for project/award ID (auto-detected if not specified)')
    parser.add_argument('--title-column', help='Column name for publication title (auto-detected if not specified)')
    parser.add_argument('--openalex-column', default='openalex_work_id',
                       help='Column name for OpenAlex work ID (default: openalex_work_id)')
    parser.add_argument('--output', help='Path to save detailed JSON report')
    parser.add_argument('--max-errors', type=int, default=100,
                       help='Maximum number of error examples to analyze (default: 100)')
    
    args = parser.parse_args()
    
    if not Path(args.benchmark).exists():
        print(f"Error: Benchmark file '{args.benchmark}' not found")
        sys.exit(1)
    if not Path(args.results).exists():
        print(f"Error: Results file '{args.results}' not found")
        sys.exit(1)
    
    try:
        benchmark, results, column_mapping = load_data(
            args.benchmark, 
            args.results,
            args.id_column,
            args.title_column,
            args.openalex_column
        )
        
        confusion = calculate_confusion_matrix(
            benchmark, 
            results, 
            column_mapping['openalex'],
            args.mode
        )
        
        metrics = calculate_metrics(confusion)
        
        error_df = analyze_errors(benchmark, results, column_mapping, args.max_errors)
        
        generate_report(
            confusion, 
            metrics, 
            error_df, 
            args.benchmark,
            args.results,
            args.mode, 
            args.output
        )
        
        return confusion, metrics, error_df
        
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()