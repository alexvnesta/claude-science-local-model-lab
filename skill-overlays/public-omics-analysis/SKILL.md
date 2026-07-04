---
name: public-omics-analysis
description: Find, validate, and analyze reusable public omics datasets without starting from raw FASTQ/BAM reprocessing. Use this skill when the user asks for public processed data, author-provided figure data, a reproducible plot from a paper, quick public-data analysis, first-pass plot, cohort comparison, subtype/group expression plot, TCGA/GEO/recount/Xena/DepMap/CELLxGENE analysis, processed matrix reuse, transposable-element/repeat-expression quick look, or TE/repeat dysregulation across cancer types. Especially use it when the question is "what public data is available and can we make an initial plot without reprocessing from zero?" Load this before generic PDF-only or cancer-portal exploration when the target is a data-backed omics paper figure or processed public matrix.
---

# Public Omics Analysis

Use this skill to turn a biological question into a defensible first-pass
public-data analysis when processed matrices already exist. This is a reuse
workflow, not a raw-processing workflow. Find the smallest public data route that
can answer the question, prove the join keys and labels are real, make a useful
plot, and state what the plot can and cannot support.

## Core Workflow

1. Translate the request into three required objects:
   - measurement matrix: expression, TE/repeat expression, methylation, copy
     number, single-cell counts, or other omics values;
   - sample/cell labels: subtype, phenotype, treatment, tissue, cell type,
     donor, or outcome;
   - join key: sample barcode, subject ID, cell barcode, accession, or feature
     identifier.

2. Search for processed public sources before considering raw reprocessing. Read
   source-specific references only when the request matches them:
   - TCGA / UCSC Xena cohort matrices and phenotype labels:
     `references/tcga-xena.md`.
   - GEO/recount/DepMap/CELLxGENE/source selection patterns:
     `references/source-patterns.md`.
   - Transposable element or repetitive element expression:
     `references/repetitive-elements.md`.
   For TE/repeat-expression requests, load the TE reference before generic
   cancer-portal queries or local artifact search. In Python, call
   `public_omics_reference("repetitive-elements")`; otherwise read
   `references/repetitive-elements.md` from this skill folder. Do not treat a
   normal gene-expression matrix as a TE matrix.

3. Build a provenance manifest before plotting:
   - source name and URL;
   - file names and checksums when a file is downloaded;
   - matrix dimensions;
   - label column used;
   - join key transformation;
   - number of samples before filtering, after filtering, and after joining.

4. Stop early if the route is not actually reusable. A proper stop is better
   than a confident plot from mismatched data. Stop when:
   - only raw FASTQ/BAM data are available and the user asked to avoid
     reprocessing;
   - the matrix exists but the requested labels cannot be joined;
   - labels are inferred from the same measurement being tested and the user
     wants an independent association claim;
   - identifiers cannot be mapped without unverifiable guessing.

5. Make a first-pass plot only after the join has been counted and inspected.
   Prefer plots that reveal distributions and group sizes:
   - expression by group: violin or box plot with sample counts;
   - many features by group: heatmap of group medians plus a distribution panel;
   - single-cell composition: stacked bars plus per-donor dots;
   - cohort overview: sample flow table and compact summary plot.

6. Interpret cautiously. A quick-look plot can support orientation and
   hypothesis generation. It is not differential expression, biomarker
   validation, causal evidence, or clinical prediction unless the analysis
   includes the required statistics and controls.

## Practical Standards

- Prefer direct public URLs over search-result snippets.
- For paper-derived figures, check Data availability, Code availability,
  supplementary/source-data links, and author package or repository archives
  before broad PDF scans, generic web scraping, or package installation.
- Do not install generic web-scraping packages such as `requests` or
  `beautifulsoup4` just to fetch a public HTML page. Use available fetch/search
  tools or the language standard library; if provenance still cannot be
  established, write blocked provenance instead of installing exploratory
  scraping dependencies.
- Prefer source references and public URLs over local `host.artifacts(...)`
  search. Use local artifact search only when the user asks to reuse existing
  artifacts, and if you do use it, print or summarize the returned artifact
  names, IDs, and provenance before relying on them.
- Verify at least the first row/header and dimensions after download.
- Record checksums for downloaded files when feasible.
- When inspecting tarballs, zip files, R packages, or repository snapshots, use
  suffix/containment checks for archive member paths because files usually live
  under a package/root prefix.
- For Bioconductor-backed R objects such as `ExpressionSet`,
  `SummarizedExperiment`, or Bioconductor annotation classes, keep package setup
  bounded and explicit. Use already available R/Bioconductor packages when
  possible; if a small missing package set blocks reading the object, install or
  request only that set through the environment's package mechanism. Do not run
  required package setup in the background unless you will wait for it and handle
  failure before plotting. If package setup fails, write a blocked provenance
  note and stop rather than making a synthetic plot.
- Use exact join counts; do not say "matched well" without numbers.
- Keep normal samples separate from tumor subtype labels. A label such as
  "normal-like" can be a cohort-defined subtype rather than normal tissue unless
  the sample type proves otherwise.
- Save the final plot and a short machine-readable provenance file with the same
  basename when possible.

## Helpful Kernel Functions

Loading this skill defines small Python helpers:

- `public_omics_reference(name)` returns bundled reference text for names such
  as `repetitive-elements`, `tcga-xena`, or `source-patterns`.
- `tcga_sample_type(barcode)` extracts TCGA sample type codes.
- `tcga_short_barcode(barcode, length=15)` normalizes TCGA sample IDs for common
  Xena joins.
- `tcga_participant_barcode(barcode)` returns the 12-character participant ID.
- `classify_repeat_feature(value)` extracts repeat class/family labels from
  common `name#class/family`, `class|family`, or metadata-like feature strings.
- `summarize_join(left_ids, right_ids)` reports overlap counts before merging.

Use these helpers for convenience, but still inspect actual source headers
because public data providers do not all use the same identifier level.
Call injected helpers as ordinary names inside the Python tool cell. Do not use
Claude Science host APIs such as `host.skills`, `kernel`, or `import kernel` to
find or call helper functions.

## Output Pattern

For a quick public-data analysis, produce:

1. A short data-route summary with URLs and join keys.
2. A sample-flow table or counts paragraph.
3. A plot artifact.
4. A cautious interpretation that distinguishes orientation from a tested claim.
5. Clear next steps for moving from quick look to defensible analysis.
