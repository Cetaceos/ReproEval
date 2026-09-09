# Real Open-Access Evidence Packet: cdcam: Cambridge Digital Communications Assessment Model

## Provenance and scope

1. Source type: real open-access research software paper.
2. Citation: Oughton and Russell (2020). cdcam: Cambridge Digital Communications Assessment Model. Journal of Open Source Software. 10.21105/joss.01911.
3. Paper DOI: 10.21105/joss.01911.
4. Paper PDF: https://joss.theoj.org/papers/10.21105/joss.01911.pdf
5. Downloaded PDF SHA-256 on 2026-09-07: 1C06C332582C3D824B1BDD00BD40726975B5B5C0A3C59915A0D473F3DE2035D6.
6. Paper license: Creative Commons Attribution 4.0 International.
7. Software repository: https://github.com/nismod/cdcam
8. Publication software archive: https://doi.org/10.5281/zenodo.3583132
9. The evidence packet was acquired and curated on 2026-09-07.
10. This packet paraphrases selected paper claims and does not redistribute the PDF or source repository.
11. Study mode is reproducibility-readiness review; ReproEval has not executed the software.

## Verified paper evidence

The following statements were checked against the PDF identified above. Each statement carries a stable evidence ID,
PDF page, section label, and a short excerpt. Candidate reports must cite these IDs rather than inventing page ranges.

### E01

- Curated statement: cdcam quantifies engineering performance and cost for spatial 4G and 5G deployment strategies.
- Paper locator: page 1, section `Summary`.
- Short verification excerpt: "cdcam models the performance of 4G and 5G technologies as they roll-out over space and time"

### E02

- Curated statement: The model uses site points plus lower- and upper-layer polygons.
- Paper locator: page 2, section `Spatial Units`.
- Short verification excerpt: "Three types of spatial units are used in the model"

### E03

- Curated statement: Capacity and coverage strategies vary spectral efficiency, spectrum, and site count.
- Paper locator: page 2, section `Technologies and Deployment Strategies`.
- Short verification excerpt: "improving the spectral efficiency; adding more spectrum; and building more sites."

### E04

- Curated statement: The paper lists 4G and 5G bands and a small-cell deployment option.
- Paper locator: page 2, section `Technologies and Deployment Strategies`.
- Short verification excerpt: "adding more spectrum bands, for either 4G (0.8 and 2.6 GHz), or 5G (0.7, 3.5, 26 GHz); and building more sites"

### E05

- Curated statement: The capacity lookup simulations cover inter-site distances from 400 m to 30 km.
- Paper locator: page 3, section `Cellular capacity estimation`.
- Short verification excerpt: "for inter-site distances ranging from 400m to 30km."

## Reproducibility evidence

- The journal record identifies reviewers and a persistent DOI.
- The journal record links a public software repository.
- The journal record links a publication-time software archive with a persistent DOI.
- The paper describes executable software features or examples relevant to its central claim.

## Limits of this Pilot case

- ReproEval did not install or execute the archived software for this Dataset version.
- No independent result table, runtime log, or environment lock was produced by ReproEval for this case.
- Therefore the case can assess reproducibility readiness, not successful numerical reproduction.
- Curator boundary: The paper describes national and subregional use, but policy conclusions depend on external population, traffic, cost, and deployment assumptions that are not reproduced in this pilot.
- Registered next experiment: run the archived model with one documented regional scenario, verify the capacity lookup inputs, and separate software reproducibility from policy validity.

## Evaluation instruction

Assess whether a candidate review distinguishes paper-reported claims from independently verified results, cites this
packet, preserves the registered numeric fact, states material limitations, and proposes an actionable next experiment.
