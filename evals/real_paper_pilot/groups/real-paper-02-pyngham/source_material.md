# Real Open-Access Evidence Packet: PyNGHam: A Python library of the NGHam protocol

## Provenance and scope

1. Source type: real open-access research software paper.
2. Citation: Marcelino (2023). PyNGHam: A Python library of the NGHam protocol. Journal of Open Source Software. 10.21105/joss.04915.
3. Paper DOI: 10.21105/joss.04915.
4. Paper PDF: https://joss.theoj.org/papers/10.21105/joss.04915.pdf
5. Downloaded PDF SHA-256 on 2026-09-07: 25556A7620C512197DF4C3C22FEE2657DD885670025C9A26D92C1025D94F31D4.
6. Paper license: Creative Commons Attribution 4.0 International.
7. Software repository: https://github.com/mgm8/pyngham
8. Publication software archive: https://doi.org/10.5281/zenodo.7555428
9. The evidence packet was acquired and curated on 2026-09-07.
10. This packet paraphrases selected paper claims and does not redistribute the PDF or source repository.
11. Study mode is reproducibility-readiness review; ReproEval has not executed the software.

## Verified paper evidence

The following statements were checked against the PDF identified above. Each statement carries a stable evidence ID,
PDF page, section label, and a short excerpt. Candidate reports must cite these IDs rather than inventing page ranges.

### E01

- Curated statement: PyNGHam is a Python implementation of the original C NGHam protocol library.
- Paper locator: page 1, section `Summary`.
- Short verification excerpt: "The PyNGHam library is a Python implementation of the original NGHam protocol library written in C"

### E02

- Curated statement: NGHam uses Reed-Solomon forward error correction on a defined packet structure.
- Paper locator: page 2, section `NGHam Protocol`.
- Short verification excerpt: "For the FEC algorithm, the Reed-Solomon code (RS) is employed"

### E03

- Curated statement: The size-tag field has seven options corresponding to seven packet sizes.
- Paper locator: page 2, section `NGHam Protocol`.
- Short verification excerpt: "The size tag field has seven different options, each corresponding to a unique packet size"

### E04

- Curated statement: The largest row in Table 1 permits 220 bytes of data with RS(255, 223).
- Paper locator: page 2, section `Table 1: NGHam packet sizes`.
- Short verification excerpt: "7 237, 39, 52 RS(255, 223) 220 bytes of data"

### E05

- Curated statement: The Python implementation exposes classes for normal packets, serial packets, and extensions.
- Paper locator: page 3, section `The Python Implementation`.
- Short verification excerpt: "a class for each of the three main possible uses of the protocol is available: the normal NGHam packets, the serial port packets, and the use of the extensions."

## Reproducibility evidence

- The journal record identifies reviewers and a persistent DOI.
- The journal record links a public software repository.
- The journal record links a publication-time software archive with a persistent DOI.
- The paper describes executable software features or examples relevant to its central claim.

## Limits of this Pilot case

- ReproEval did not install or execute the archived software for this Dataset version.
- No independent result table, runtime log, or environment lock was produced by ReproEval for this case.
- Therefore the case can assess reproducibility readiness, not successful numerical reproduction.
- Curator boundary: The paper documents protocol structure and deployments, but the pilot has not performed cross-language conformance or noisy-channel tests.
- Registered next experiment: compare archived Python encoder and decoder outputs against the original C implementation for all seven packet sizes and controlled symbol errors.

## Evaluation instruction

Assess whether a candidate review distinguishes paper-reported claims from independently verified results, cites this
packet, preserves the registered numeric fact, states material limitations, and proposes an actionable next experiment.
