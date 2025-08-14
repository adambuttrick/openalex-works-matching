# OpenAlex Matching Evaluation

Benchmarking utility for assessing precision and recall of OpenAlex work matching.


## Installation
```bash
pip install -r requirements.txt
```


## Usage

```bash
# Basic usage (auto-detects columns)
python evaluate_matching.py benchmark.csv results.csv

# Evaluate only overlapping products
python evaluate_matching.py benchmark.csv results.csv --mode overlap

# Specify custom columns
python evaluate_matching.py benchmark.csv results.csv \
  --id-column grant_id \
  --title-column paper_title \
  --openalex-column work_id

# Save detailed report
python evaluate_matching.py benchmark.csv results.csv --output report.json
```

## Input Format

Both CSV files must contain:
- Project/award ID column (auto-detected: project_id, award_id, grant_id, id)
- Title column (auto-detected: product_title, title, publication_title, paper_title)
- OpenAlex work ID column (default: openalex_work_id)

## Output

- Console: Confusion matrix, precision/recall/accuracy, F-scores, error summary
- Optional JSON: Detailed metrics and configuration
- Optional CSV: Error cases with details

## Evaluation Modes

- `full`: Evaluates all unique products across both datasets
- `overlap`: Only evaluates products present in both datasets

## Metrics

- **Precision**: % of predicted matches that are correct
- **Recall**: % of actual matches that were found  
- **F-scores**: F0.5 (precision-weighted), F1 (balanced), F1.5 (recall-weighted)
- **Error types**: False Positives, False Negatives, Wrong Matches