# Source Patterns

Use this reference to choose public processed data sources before falling back to
raw reprocessing.

## Selection Order

1. A processed matrix published by the method or study authors.
2. A curated hub with stable sample metadata and direct downloads.
3. A public repository supplementary file with enough metadata to join samples.
4. Raw sequence archives only when the user explicitly accepts reprocessing.

## Common Sources

| Source | Good for | First checks |
|---|---|---|
| UCSC Xena | TCGA, TARGET, GTEx, phenotype and molecular matrices | Cohort page, sampleMap path, phenotype columns, sample ID level |
| GEO | Study-level processed matrices and annotations | Series Matrix, supplementary files, platform IDs, sample table |
| recount3 | Uniform RNA-seq coverage/count summaries | Project ID, gene/exon level, phenotype fields |
| DepMap | Cell-line expression, mutation, dependency, drug response | Release version, cell-line ID mapping, lineage labels |
| cBioPortal | Cancer study clinical/mutation/CNA summaries | Study ID, data type, sample list, clinical attributes |
| CELLxGENE | Single-cell matrices and cell metadata | Organism, tissue, disease, assay, donor/cell metadata |
| Synapse / Figshare / Zenodo / OSF | Author-published processed outputs | DOI/accession, license, checksums, file dictionary |

## Discovery Queries

Prefer precise searches that include the data type and "processed matrix" terms:

- `{disease} {omics type} processed matrix public download`
- `{cohort} phenotype matrix sampleMap Xena`
- `{study accession} supplementary expression matrix`
- `{method name} data package RDS expression matrix`
- `{data type} {label} public cohort metadata`

If a search tool budget is limited, search for the source family directly
instead of only the broad biological question. For example, search for the
method name, cohort, data type, and processed-matrix terms together rather than
only a disease and pathway phrase.

## Provenance Manifest Fields

Record a compact manifest alongside the output:

```json
{
  "question": "...",
  "sources": [
    {
      "name": "...",
      "url": "...",
      "local_file": "...",
      "sha256": "...",
      "rows": 0,
      "columns": 0
    }
  ],
  "join": {
    "left_key": "...",
    "right_key": "...",
    "normalization": "...",
    "left_n": 0,
    "right_n": 0,
    "joined_n": 0
  },
  "filters": ["..."],
  "label_column": "...",
  "plot_file": "..."
}
```

## Stop Conditions

Stop and explain the gap when the analysis would require any of these hidden
assumptions:

- label source does not identify the same sample unit as the matrix;
- sample IDs require manual title/name matching rather than stable identifiers;
- requested groups have too few samples to visualize honestly;
- data are normalized in incompatible units across cohorts;
- source is only a paper figure with no downloadable values;
- user asked for "without reprocessing" but only raw archives are available.
