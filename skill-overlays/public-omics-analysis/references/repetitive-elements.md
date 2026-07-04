# Repetitive Element And TE Expression

Use this reference when the request involves transposable elements, repetitive
elements, repeat classes, repeat subfamilies, ERVs, LINEs, SINEs, satellites, or
repeat-expression plots.

## Prefer Precomputed TE Matrices For Quick Looks

Short-read repeat expression is not the same as ordinary gene expression.
Ambiguous mapping, locus/subfamily aggregation, and annotation version matter.
For a quick public-data plot, prefer a published processed TE matrix whose method
and units are known. Do not substitute a gene-expression matrix from Xena or
recount and call it TE expression.

## Published Processed TE Sources

Useful quick-look sources usually come from method papers, author data packages,
curated supplementary files, or cohort portals that expose both a processed TE
matrix and auditable sample metadata. Prefer sources that document:

- repeat quantification method and annotation version;
- feature resolution, such as locus, subfamily, family, or class;
- units or transformation, such as counts, TPM, CPM, logCPM, or normalized
  scores;
- sample identifiers that can be joined to phenotype, subtype, tissue, or cohort
  labels;
- feature metadata columns for repeat name, class, family, and genomic scope.

When an author source is an R package or archive, inspect the package metadata,
script paths, and data-object paths in the current archive. Match files by
suffix or containment rather than bare filenames because archives usually have a
root prefix. If figure scripts use package-relative paths such as
`system.file(...)`, record the package name from `DESCRIPTION` and resolve those
paths back to source-archive members before deciding that data are missing.

R-native processed matrices may be `ExpressionSet` or `SummarizedExperiment`
objects. In a valid route, check the relevant accessors or object slots for:

- expression matrix values and dimensions;
- sample metadata, including cohort or phenotype labels;
- feature metadata, including repeat name, class, family, and genomic scope.

`Biobase` and `BiocGenerics` are common dependencies for older Bioconductor data
objects. Use available R/Bioconductor packages when possible. If missing
packages block reading a real object, keep setup bounded to the package set
needed for that object and record the environment change in provenance. If setup
fails, write a blocked provenance note rather than making a synthetic TE plot.

## Example Pattern: Cancer TE Expression By Tumor Subtype

This is a reusable route pattern, not a precomputed answer. Recount the samples
from the current files every time.

1. Find a processed TE matrix for the cancer cohort, preferably with documented
   repeat feature metadata and sample-level identifiers.
2. Read the matrix with the format-appropriate tooling. For R-native
   Bioconductor objects, use the object accessors rather than converting through
   an unrelated language bridge.
3. Filter to the requested disease and sample type using explicit metadata
   columns or stable barcode/sample-type fields.
4. Find an independent subtype or phenotype label source, such as cohort
   clinical metadata, a phenotype matrix, or author-provided annotations.
5. Join matrix samples to labels at the same identifier level, then report
   before-filter, after-filter, and joined sample counts.
6. Use a subtype label column only after checking coverage and definitions.
   Report the exact label column and final group counts.
7. Summarize TE expression by biologically interpretable repeat group, for
   example per-sample median expression within LTR, DNA, LINE, SINE, satellite,
   and retroposon-like classes when those classes exist in the feature metadata.
8. Plot either:
   - heatmap of subtype medians plus class-level violins; or
   - one violin/box plot per repeat class with sample counts.

## Interpretation Rules

- Call the result a quick-look class-level summary, not differential expression.
- State the source-specific units and transformation used by the processed TE
  matrix.
- Avoid claims about individual loci unless the matrix supports that resolution.
- Move to subfamily-level testing before making a biological claim, because
  class-level medians can hide specific repeat families.
- Control for purity, batch, immune/stromal composition, and multiple testing
  before claiming subtype-specific repeat dysregulation.
