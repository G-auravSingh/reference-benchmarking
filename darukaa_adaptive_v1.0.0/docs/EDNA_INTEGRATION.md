# eDNA / Metagenomics Integration

The package treats environmental DNA as a distinct evidence stream. It does not equate every taxonomic assignment with a direct biodiversity observation or a live census.

## Current Nandoshi Phase-1 evidence model

The supplied Nandoshi report describes four independent sampling stations, sampled on 28 May 2026, with 250 ml water per station and a shotgun metagenomic workflow. The run generated 8.01 million high-confidence taxonomically assigned reads and 14,375 taxonomic assignments. The report explicitly states that assignments are database matches whose certainty depends on read length, genome coverage, database representation and classification, and that eDNA records recent biological material rather than confirming that every detection was alive, locally established or active at sampling.

The package therefore separates eDNA evidence into:

- **Measured:** sequencing outputs and directly reported molecular quantities.
- **Indicated:** signals such as cyanobacterial, human-associated or reducing-microbe fractions that point toward an ecological pressure or condition and require confirmation.
- **Inferred:** functional-potential interpretations such as nutrient-cycling or pollutant-degradation capacity.
- **Unresolved:** findings requiring targeted validation before interpretation is strengthened.

Current structured metrics include broad molecular assignment output, cyanobacterial fraction, human-associated fraction and reducing-microbe fraction. Broad shotgun taxonomic assignment count is **not** treated as C3 fauna richness because the Nandoshi report includes bacteria, archaea, viruses, plants, algae, fungi and other eukaryotic assignments. A future `edna_fauna_taxonomic_richness` metric is reserved for a fauna-targeted molecular workflow.

## Scoring rule

An eDNA metric enters the shared scoring engine only when:

1. the metric has an explicit pillar and direction;
2. the sampling/laboratory/bioinformatics protocol is comparable to the reference;
3. a reference value/distribution is supplied or generated through an approved reference module; and
4. the reference passes the same sample-size and uncertainty-approval gates as other evidence types.

Otherwise the eDNA record remains evidence-only in the report.

## Confirmation examples from the Nandoshi report

Cyanobacterial signal should be checked with chlorophyll-a/phycocyanin, microscopy or cell counts, toxin-gene assays and toxin concentration where relevant. Human-associated/fecal-associated signals require source-tracking and conventional water-quality confirmation. Reducing/oxygen-limited signals require direct dissolved-oxygen measurements and related chemistry.

This conservative treatment is intentional: eDNA complements water chemistry, bioacoustics, field fauna, habitat and Earth-observation measurements rather than replacing them.
