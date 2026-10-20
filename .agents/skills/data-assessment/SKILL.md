---
name: data-assessment
description: Assess a dataset and its management practices before data preparation or modeling. Use the seven DAMA-DMBOK environmental elements and the nine revised data-quality dimensions; do not use for transformation or table-spec authoring alone.
---

# Data Assessment

Assess the dataset and its management practices with traceable evidence. Treat
`raw` (source-preserving data), `processed` (data transformed by documented
rules), and `datamart` (purpose-specific data) as the default logical layers.
Confirm physical storage and existing conventions before describing them; this
skill alone does not establish a storage architecture.

## Required references

- Read [the seven environmental elements](references/environmental-elements.md)
  before assessing management practices. Evaluate every element.
- Read [the nine data quality dimensions](references/data-quality-dimensions.md)
  before profiling quality. Evaluate every dimension separately from the seven
  management elements. Use the exact English names in those references.

## Workflow

1. Establish the dataset, business use, time period, location, format, owner,
   existing definitions, and quality criteria. Record unavailable inputs as
   unknown rather than assuming they exist.
2. Check data volume, query cost, and sensitivity before profiling. Choose a
   justified full-population or bounded sample approach. Prefer read-only
   metadata and aggregates; do not bring raw sensitive values into the
   conversation or report. Record scope and methods, and never present sample
   results as full-population measurements.
3. For each of the seven environmental elements, record an assessment question,
   evidence, current finding, gap, recommended action, and unresolved question.
   Use documents or owner interviews for organizational facts that data values
   cannot establish.
4. For each of the nine quality dimensions, record the target and rule, method,
   measured result, business threshold, conclusion, and evidence or reason it
   could not be evaluated. Do not mark a dimension as passing without the
   reference data or business rule needed to judge it.
5. Map the observed `source → raw → processed → datamart` flow, missing links,
   priorities, and candidate improvements. Present data-changing choices such
   as imputation, exclusion, outlier handling, rounding, deduplication, or a
   change in aggregation grain as proposals, not approved rules.

## Deliverable

Use the existing report format, or Markdown if none exists. Include the scope
and method, inventory by layer, all seven management assessments, all nine
quality assessments, supporting evidence, unknowns, and prioritized issues.
Record enough query and sampling detail to reproduce each measurement. Mark
unmeasured items explicitly instead of leaving blank results.
