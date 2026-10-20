---
name: table-definition
description: Create or update table definition documents for existing or planned raw, processed, and datamart tables. Use verified schemas for existing tables and approved requirements for proposed tables.
---

# Table Definition

Create table definition documents from verified existing schemas or approved
requirements for proposed tables. Use `raw`, `processed`, and `datamart` as the
default logical layers and make each table's purpose and lineage traceable.
Confirm actual storage locations, database technology, and SQL dialect from
the target environment.

## Workflow

1. Inspect the existing tables or files and their actual schemas, or the
   approved requirements for proposed tables. Also inspect existing
   definitions, assessments, and approved preprocessing rules. Use the existing
   document format, or Markdown if none exists. Label every unimplemented
   table definition as a **design proposal**.
2. For each table, record its layer, logical and physical names, purpose, row
   grain, sources, consumers, refresh method and frequency, owner, primary and
   foreign keys, constraints, sensitivity classification, and quality checks.
   Mark unavailable facts as `To confirm`, with the owner and question.
3. For each column, record physical and logical names, meaning, type and length,
   nullability, default, keys and constraints, source column, derivation, and
   sensitivity classification. Do not infer a business meaning or constraint
   from a column name alone.
4. For `raw`, record source correspondence and acquisition conditions. For
   `processed`, record approved conversions, standardization, exclusions, and
   combinations. For `datamart`, record purpose, grain, measure formulas, and
   aggregation conditions. Keep undecided rules and measures separate from
   confirmed definitions.
5. Compare existing-table definitions with actual DDL, file schemas, and
   processing results. List differences in columns, types, nullability, keys,
   lineage, and measures; apply only confirmed corrections. Check design
   proposals against approved requirements and flag the need for a later
   comparison with the implemented schema.

## Deliverable

Produce a table inventory, table and column definitions, the
`source → raw → processed → datamart` mapping, source evidence, reconciliation
results, and unresolved decisions. Creating the document alone does not change
database schemas or production data unless those changes are in the request.
