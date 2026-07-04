# TCGA And UCSC Xena Patterns

Use this reference for TCGA quick-look analyses that need public processed
matrices and clinical/subtype labels.

## Useful URLs

- TCGA Xena hub root: `https://tcga.xenahubs.net`
- Direct download pattern:
  `https://tcga.xenahubs.net/download/<cohort>.sampleMap/<matrix_name>`
- Common clinical/phenotype matrix names include cohort-specific
  `*_clinicalMatrix`, `phenotype`, or curated sample-map tables exposed under
  the cohort's `sampleMap` directory.
- Molecular matrix names are cohort and hub specific. Inspect the cohort's Xena
  file listing or hub metadata rather than guessing from another disease.

Always follow redirects when downloading from Xena; the public hub commonly
redirects to S3.

## TCGA Barcode Levels

TCGA barcodes encode different biological units. Match at the level the source
actually uses:

| Level | Example | Use |
|---|---|---|
| participant | `TCGA-AB-1234` | patient-level clinical labels |
| sample | `TCGA-AB-1234-01` | tumor/normal sample labels |
| vial/analyte/aliquot | `TCGA-AB-1234-01A-...` | assay-level files |

Common quick-look joins:

- matrix columns at aliquot level to Xena sample clinical rows: use the first 15
  characters when Xena rows are `TCGA-XX-YYYY-01`;
- patient-level clinical labels: use the first 12 characters;
- primary tumor filter: sample type code `01`;
- solid normal filter: sample type code `11`.

Inspect source headers before truncating. Do not use a 12-character patient join
when multiple samples per patient matter.

## Cohort Subtype Labels

Clinical matrices can contain multiple related subtype, cluster, or phenotype
columns. For a first-pass group plot:

- list candidate label columns and their non-missing counts;
- prefer the label column whose definition matches the requested comparison;
- do not silently substitute an integrated cluster, risk group, or assay-derived
  class for a direct subtype label;
- record whether labels are tumor labels, tissue labels, patient labels, or
  assay labels before plotting.

Report which label column you used and the sample counts per subtype. Treat
normal-like labels as cohort-defined subtype labels unless the sample type or
metadata explicitly indicates normal tissue.

## Minimum Checks

Before plotting:

1. Print matrix dimensions.
2. Print clinical matrix dimensions.
3. Count sample types in the matrix.
4. Count label coverage before and after joining.
5. Count final samples per plotted group.

If a group is small, keep it visible but caveat it rather than silently dropping
it unless there is a stated threshold.
