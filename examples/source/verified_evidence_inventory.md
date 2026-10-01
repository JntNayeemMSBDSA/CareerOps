# Fictional verified evidence

All organizations, chronology, observations, and measurements below are invented for tests.


## EXP-101 - Museum attendance analytics

**Organization/context:** Harborlight Museum Cooperative
**Role:** Analytics Engineer
**Period:** Feb 2017 - Nov 2019
- Synthetic evidence only.

### Technical methods
- Built a SQL and Python attendance pipeline for 18 museum galleries using incremental loads, schema checks, and pytest reconciliation tests.
- Processed 240,000 fictional ticket events in DuckDB and Parquet to validate visitor counts before dashboard publication.

### Tools and platforms
- SQL, Python, pandas, DuckDB, Parquet, dbt, ETL/ELT, pytest

### Data and scale
- Processed 240,000 fictional ticket events in DuckDB and Parquet to validate visitor counts before dashboard publication.

### Claim boundaries / integrity rules
- Fictional measurements are for tests only. Do not attribute work to an employer other than this entity.
- Modeled predictions are not realized business results.

### Technical methods
- SQL reconciliation joins verified source-to-output record counts before the reporting snapshot was released.
- Python pytest regression tests checked null standardization and duplicate ticket keys.
### Core outputs
- Validated attendance dashboard and immutable Parquet reporting snapshot.
### Data and scale
- Fictional ticket records: 240,000
- Museum galleries: 18

## EXP-102 - Parcel service monitoring

**Organization/context:** Maple Lantern Logistics
**Role:** Data Analyst
**Period:** Mar 2020 - Aug 2023
- Synthetic evidence only.

### Technical methods
- Designed a Power BI reporting model for 27 fictional delivery zones using DAX measures and SQL reconciliation queries.
- Documented data quality rules and reviewed missing scan records with dispatch coordinators to maintain weekly reporting.

### Tools and platforms
- SQL, Power BI, DAX, Power Query, Excel, PostgreSQL

### Data and scale
- Documented data quality rules and reviewed missing scan records with dispatch coordinators to maintain weekly reporting.

### Claim boundaries / integrity rules
- Fictional measurements are for tests only. Do not attribute work to an employer other than this entity.
- Modeled predictions are not realized business results.

### Technical methods
- SQL reconciliation queries compared shipment totals with the reporting model.
- DAX measure tests verified filter context and missing scan handling.
### Core outputs
- Weekly delivery-zone dashboard and data-quality review workbook.
### Data and scale
- Fictional delivery zones: 27
- Fictional shipment records: 52,800

## PRJ-101 - Library return-risk classifier

**Organization/context:** Independent fictional project
**Role:** Project Owner
**Period:** Jan 2024 - Apr 2024
- Synthetic evidence only.

### Technical methods
- Trained a logistic classifier on 8,400 synthetic book-loan records using stratified cross-validation and leakage checks.
- Compared classification precision and recall across folds; kept predictive results separate from realized business outcomes.

### Tools and platforms
- Python, pandas, NumPy, Classification, Feature Engineering, Model Evaluation, Cross-validation, Git

### Data and scale
- Compared classification precision and recall across folds; kept predictive results separate from realized business outcomes.

### Claim boundaries / integrity rules
- Fictional measurements are for tests only. Do not attribute work to an employer other than this entity.
- Modeled predictions are not realized business results.

### Technical methods
- Stratified cross-validation evaluated classification precision and recall.
- pytest leakage tests checked feature timing against synthetic return labels.
### Core outputs
- Classification evaluation notebook and fold-level metrics report.
### Data and scale
- Synthetic book-loan records: 8,400
- Evaluation folds: 5

## PRJ-102 - Community garden measurement study

**Organization/context:** Independent fictional project
**Role:** Project Owner
**Period:** Jun 2024 - Sep 2024
- Synthetic evidence only.

### Technical methods
- Analyzed 96 synthetic garden plots with bootstrap confidence intervals and documented measurement uncertainty.
- Validated notebook inputs with pytest and GitHub Actions before publishing reproducible figures.

### Tools and platforms
- Python, Hypothesis Testing, Confidence Intervals, Data Visualization, GitHub Actions, Ruff

### Data and scale
- Validated notebook inputs with pytest and GitHub Actions before publishing reproducible figures.

### Claim boundaries / integrity rules
- Fictional measurements are for tests only. Do not attribute work to an employer other than this entity.
- Modeled predictions are not realized business results.

### Technical methods
- Bootstrap confidence intervals quantified sampling uncertainty.
- pytest input validation and notebook checksum tests protected reproducible measurements.
### Core outputs
- Measurement uncertainty report and reproducible notebook.
### Data and scale
- Synthetic garden plots: 96
- Synthetic measurements: 384
