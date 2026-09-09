# Real Open-Access Evidence Packet: itmlogic: The Irregular Terrain Model by Longley and Rice

## Provenance and scope

1. Source type: real open-access research software paper.
2. Citation: Oughton, Russell, Johnson, Yardim, and Kusuma (2020). itmlogic: The Irregular Terrain Model by Longley and Rice. Journal of Open Source Software. 10.21105/joss.02266.
3. Paper DOI: 10.21105/joss.02266.
4. Paper PDF: https://joss.theoj.org/papers/10.21105/joss.02266.pdf
5. Downloaded PDF SHA-256 on 2026-09-07: 5840DAF288A56B46C3253E9E392BA35A1E9E08D3F6DE11E808C693F9E8B379C4.
6. Paper license: Creative Commons Attribution 4.0 International.
7. Software repository: https://github.com/edwardoughton/itmlogic
8. Publication software archive: https://doi.org/10.5281/zenodo.3931350
9. The evidence packet was acquired and curated on 2026-09-07.
10. This packet paraphrases selected paper claims and does not redistribute the PDF or source repository.
11. Study mode is reproducibility-readiness review; ReproEval has not executed the software.

## Verified paper evidence

The following statements were checked against the PDF identified above. Each statement carries a stable evidence ID,
PDF page, section label, and a short excerpt. Candidate reports must cite these IDs rather than inventing page ranges.

### E01

- Curated statement: itmlogic is described as a Python implementation of the Longley-Rice Irregular Terrain Model.
- Paper locator: page 1, section `Summary`.
- Short verification excerpt: "This paper describes the itmlogic package, which provides a Python implementation of the Longley-Rice Irregular Terrain Model."

### E02

- Curated statement: The model predicts propagation-loss statistics from radio, climate, and terrain inputs.
- Paper locator: page 1, section `Summary`.
- Short verification excerpt: "itmlogic is capable of predicting the the statistics of propagation loss"

### E03

- Curated statement: Height inputs are in metres while ranges are in kilometres.
- Paper locator: page 2, section `Spatial Units`.
- Short verification excerpt: "transmitter and receiver heights above the local terrain are specified in meters while ranges are specified in kilometers."

### E04

- Curated statement: Point-to-point mode uses up to 600 terrain-profile points.
- Paper locator: page 3, section `Prediction modes`.
- Short verification excerpt: "Point-to-point mode uses a sample of up to 600 points from the terrain profile"

### E05

- Curated statement: Median loss estimates may be consumed by wider link-budget and infrastructure assessments.
- Paper locator: page 3, section `Applications`.
- Short verification excerpt: "The median propagation loss estimates produced by itmlogic can be used with other link budget estimation models"

## Reproducibility evidence

- The journal record identifies reviewers and a persistent DOI.
- The journal record links a public software repository.
- The journal record links a publication-time software archive with a persistent DOI.
- The paper describes executable software features or examples relevant to its central claim.

## Limits of this Pilot case

- ReproEval did not install or execute the archived software for this Dataset version.
- No independent result table, runtime log, or environment lock was produced by ReproEval for this case.
- Therefore the case can assess reproducibility readiness, not successful numerical reproduction.
- Curator boundary: A Python implementation claim does not establish numerical equivalence to the reference Fortran or C++ implementations across propagation regimes.
- Registered next experiment: run archived cross-implementation fixtures over area and point-to-point modes, including unit-boundary cases, and report numerical tolerances.

## Evaluation instruction

Assess whether a candidate review distinguishes paper-reported claims from independently verified results, cites this
packet, preserves the registered numeric fact, states material limitations, and proposes an actionable next experiment.
