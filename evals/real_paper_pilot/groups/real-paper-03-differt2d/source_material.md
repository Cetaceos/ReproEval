# Real Open-Access Evidence Packet: DiffeRT2d: A Differentiable Ray Tracing Python Framework for Radio Propagation

## Provenance and scope

1. Source type: real open-access research software paper.
2. Citation: Eertmans, Oestges, and Jacques (2024). DiffeRT2d: A Differentiable Ray Tracing Python Framework for Radio Propagation. Journal of Open Source Software. 10.21105/joss.06915.
3. Paper DOI: 10.21105/joss.06915.
4. Paper PDF: https://joss.theoj.org/papers/10.21105/joss.06915.pdf
5. Downloaded PDF SHA-256 on 2026-09-07: E47AD55BFAC6021A3C25D93363D1BBECBBC0DD3FCB561F5923EA79D86450B384.
6. Paper license: Creative Commons Attribution 4.0 International.
7. Software repository: https://github.com/jeertmans/DiffeRT2d
8. Publication software archive: https://doi.org/10.5281/zenodo.12600658
9. The evidence packet was acquired and curated on 2026-09-07.
10. This packet paraphrases selected paper claims and does not redistribute the PDF or source repository.
11. Study mode is reproducibility-readiness review; ReproEval has not executed the software.

## Verified paper evidence

The following statements were checked against the PDF identified above. Each statement carries a stable evidence ID,
PDF page, section label, and a short excerpt. Candidate reports must cite these IDs rather than inventing page ranges.

### E01

- Curated statement: DiffeRT2d is presented as an open-source two-dimensional differentiable ray tracer using JAX.
- Paper locator: page 1, section `Summary`.
- Short verification excerpt: "We present DiffeRT2d, a 2D Open Source differentiable ray tracer"

### E02

- Curated statement: The framework supports image, path-minimization, and Min-Path-Tracing methods.
- Paper locator: page 2, section `Statement of Need`.
- Short verification excerpt: "path minimization based on Fermat's principle"

### E03

- Curated statement: Its received-power model is a rough approximation that ignores local wave phase.
- Paper locator: page 2, section `Easy to Use Commitment`.
- Short verification excerpt: "a rough approximation of the received power, which ignores the local phase of the wave"

### E04

- Curated statement: The Figure 2 reproduction code configures 1000 minimization steps.
- Paper locator: page 4, section `Usage Examples - Exploring Metasurfaces and More`.
- Short verification excerpt: "path_cls_kwargs={"steps": 1000}"

### E05

- Curated statement: The authors state an aim of maintaining 100% code coverage, not a measured guarantee in this Pilot.
- Paper locator: page 5, section `Stability and releases`.
- Short verification excerpt: "we aim to maintain a code coverage metric of 100%."

## Reproducibility evidence

- The journal record identifies reviewers and a persistent DOI.
- The journal record links a public software repository.
- The journal record links a publication-time software archive with a persistent DOI.
- The paper describes executable software features or examples relevant to its central claim.

## Limits of this Pilot case

- ReproEval did not install or execute the archived software for this Dataset version.
- No independent result table, runtime log, or environment lock was produced by ReproEval for this case.
- Therefore the case can assess reproducibility readiness, not successful numerical reproduction.
- Curator boundary: A visually similar coverage map would not by itself validate electromagnetic fidelity because the stated model omits local phase and does not compute full electromagnetic fields.
- Registered next experiment: execute the archived v0.3.4 Figure 2 script, preserve environment metadata, compare the generated map, and keep physical-fidelity claims within the paper's approximation boundary.

## Evaluation instruction

Assess whether a candidate review distinguishes paper-reported claims from independently verified results, cites this
packet, preserves the registered numeric fact, states material limitations, and proposes an actionable next experiment.
