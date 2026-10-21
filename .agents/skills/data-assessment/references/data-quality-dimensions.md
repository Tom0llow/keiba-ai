# Nine DAMA-DMBOK2 Revised Data Quality Dimensions

## Source and interpretation

[DAMA International's DMBOK2 Revision summary, Chapter 13](https://www.damadmbok.org/dmbok2-revisions)
lists the former eight standard dimensions, adds **Currency**, and replaces
the former term **Reasonability** with **Reasonableness**. Those changes yield
the nine revised English names used as the headings below.
The public change summary does not publish the revised book's full dimension
definitions. The assessment questions here are operational guidance for this
skill, not attributed DAMA definitions or universal thresholds.

For every dimension, record the target data and population, business rule or
reference, measurement method, observed result, threshold, conclusion, and
evidence. Mark a dimension `Not assessed` when the required rule, reference,
access, or sample is unavailable. Mark it `Not applicable` only with a reason
that identifies the use case and decision owner. Do not convert an absent
criterion into a passing result.

## 1. Accuracy

- **Assessment question:** Do recorded values agree with an independently
  trusted observation or reference for the same entity and time?
- **Evidence to seek:** A verified source of truth and a documented comparison
  sample. Without a trusted reference, report the dimension as not assessed.

## 2. Validity

- **Assessment question:** Do values satisfy the declared type, format, domain,
  and business rules applicable to the field?
- **Evidence to seek:** Approved schemas, permitted-value lists, rule checks,
  and counts of invalid values.

## 3. Completeness

- **Assessment question:** Are required records and required attributes present
  for the defined population and purpose?
- **Evidence to seek:** Population expectations, mandatory-field rules, missing
  record counts, and missing-value counts.

## 4. Integrity

- **Assessment question:** Are declared relationships and structural constraints
  preserved across the relevant records and tables?
- **Evidence to seek:** Declared keys and relationships, orphan counts, and
  constraint-check results. This is the skill's operational test for Integrity.

## 5. Uniqueness/Deduplication

- **Assessment question:** Does each business entity or event occur only as many
  times as allowed at the declared row grain?
- **Evidence to seek:** Approved business keys, grain definitions, duplicate
  counts, and reviewed cases where repeated records are legitimate.

## 6. Timeliness

- **Assessment question:** Was the data available within the time window needed
  by its intended process or consumer?
- **Evidence to seek:** Event, receipt, processing, and delivery timestamps,
  with an agreed service window. Here Timeliness concerns delivery timing.

## 7. Reasonableness

- **Assessment question:** Are values and combinations plausible under
  documented domain expectations, even when they pass formal validity checks?
- **Evidence to seek:** Approved expected ranges or patterns and a reviewed
  count of exceptions. Statistical rarity alone is not a defect decision.

## 8. Consistency

- **Assessment question:** Do representations of the same fact agree across the
  datasets, records, and rules being compared?
- **Evidence to seek:** Reconciliation rules, comparison results, and identified
  disagreements. Here Consistency concerns agreement among representations.

## 9. Currency

- **Assessment question:** Does each value reflect the latest known applicable
  state at the agreed reference time?
- **Evidence to seek:** Effective dates, source update times, refresh history,
  and a business rule for when a value becomes stale. Here Currency concerns
  current state, separately from delivery timing under Timeliness.
