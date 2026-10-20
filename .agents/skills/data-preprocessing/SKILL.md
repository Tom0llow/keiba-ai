---
name: data-preprocessing
description: Plan, preview, and perform approved data cleaning and preparation from raw to processed or datamart. Use when source data needs reproducible transformations and impact checks; not for assessment-only requests.
---

# Data Preprocessing

Prepare data with a recorded reason and impact for each transformation.
`raw` holds source-preserving data, `processed` holds data transformed by
reproducible rules, and `datamart` holds data at a defined business grain for a
defined use. These are logical layers; confirm the actual storage format and
location in the target environment.

## Workflow

1. Inspect the source, purpose, scope, existing pipeline, definitions, and
   tests. Carry forward any assessment findings and unknowns.
2. Make a candidate rule table. For every rule, record inputs, outputs, **Why /
   Impact / Validation**, affected rows or columns, exception handling, and
   decision owner. Confirm type and text normalization when they could change
   business meaning.
3. Preview material choices, including missing-value treatment, exclusion,
   outlier handling, rounding, deduplication, joins, and aggregation grain.
   Show estimated changes to counts or distributions and obtain a decision
   before applying them. Do not fill undecided rules with convenient defaults.
4. Test with temporary output first. Compare input and output counts,
   excluded or combined records, key uniqueness, missingness, types, ranges,
   and referential integrity as relevant. Investigate unexplained differences
   between repeated runs.
5. Apply approved rules using the existing implementation pattern. Preserve
   the `raw` source and store transformed output so it is distinguishable as
   `processed`. Create a `datamart` only when its purpose, row grain, measures,
   and aggregation rules are defined. Before replacing or publishing existing
   data, present the trial results, exact destination or audience, impact, and
   recovery approach, then obtain explicit authorization for that action.

## Deliverable

Leave the transformation rules, executable processing or reproducible steps,
source-to-output mapping, trial and final validation results, and unresolved
exceptions. Keep before and after data identifiable, with each transformation's
reason, impact, and validation traceable. Reconcile confirmed columns, types,
and derivations with any existing table definition document.
