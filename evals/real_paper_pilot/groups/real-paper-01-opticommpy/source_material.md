# Real Open-Access Evidence Packet: OptiCommPy: Open-source Simulation of Fiber Optic Communications with Python

## Provenance and scope

1. Source type: real open-access research software paper.
2. Citation: da Silva and Herbster (2024). OptiCommPy: Open-source Simulation of Fiber Optic Communications with Python. Journal of Open Source Software. 10.21105/joss.06600.
3. Paper DOI: 10.21105/joss.06600.
4. Paper PDF: https://joss.theoj.org/papers/10.21105/joss.06600.pdf
5. Downloaded PDF SHA-256 on 2026-09-07: 146FF130EB0B8DF3E2C6F8232AE889367D83CC148DA8269FE09D1714EFB6DD3E.
6. Paper license: Creative Commons Attribution 4.0 International.
7. Software repository: https://github.com/edsonportosilva/OptiCommPy
8. Publication software archive: https://doi.org/10.5281/zenodo.11450597
9. The evidence packet was acquired and curated on 2026-09-07.
10. This packet paraphrases selected paper claims and does not redistribute the PDF or source repository.
11. Study mode is reproducibility-readiness review; ReproEval has not executed the software.

## Verified paper evidence

The following statements were checked against the PDF identified above. Each statement carries a stable evidence ID,
PDF page, section label, and a short excerpt. Candidate reports must cite these IDs rather than inventing page ranges.

### E01

- Curated statement: OptiCommPy is presented as an open-source alternative for optical-communication education and research.
- Paper locator: page 2, section `OptiCommPy code structure`.
- Short verification excerpt: "OptiCommPy is intended to be an open-source alternative simulation tool for educational and research purposes."

### E02

- Curated statement: The optic package has five top-level subpackages: comm, models, dsp, utils, and plot.
- Paper locator: page 2, section `OptiCommPy code structure`.
- Short verification excerpt: "the package is named optic, containing five sub-packages: comm, models, dsp, utils, and plot."

### E03

- Curated statement: The comm.metrics module includes BER, SER, EVM, MI, and GMI transmission metrics.
- Paper locator: page 2, section `OptiCommPy code structure`.
- Short verification excerpt: "metrics, such as bit-error-rate (BER), symbol-error-rate (SER), error vector magnitude (EVM), mutual information (MI), and generalized mutual information (GMI)"

### E04

- Curated statement: The documentation describes a getting-started example intended to reproduce the Figure 2 curves.
- Paper locator: page 3, section `Examples of usage`.
- Short verification excerpt: "a getting started example that demonstrates some of the core features of OptiCommPy and reproduces the curves displayed in Fig. 2."

### E05

- Curated statement: The repository is reported to include advanced simulation examples and GPU speedup benchmarks.
- Paper locator: page 3, section `Examples of usage`.
- Short verification excerpt: "Benchmarks quantifying the speedup achieved by using GPU acceleration are also provided."

## Reproducibility evidence

- The journal record identifies reviewers and a persistent DOI.
- The journal record links a public software repository.
- The journal record links a publication-time software archive with a persistent DOI.
- The paper describes executable software features or examples relevant to its central claim.

## Limits of this Pilot case

- ReproEval did not install or execute the archived software for this Dataset version.
- No independent result table, runtime log, or environment lock was produced by ReproEval for this case.
- Therefore the case can assess reproducibility readiness, not successful numerical reproduction.
- Curator boundary: The paper describes reproducible examples, but this pilot has not checked numerical agreement with Figure 2 or GPU benchmark values.
- Registered next experiment: run the archived Figure 2 example in a pinned environment and compare exported BER and Q-factor curves with the paper.

## Evaluation instruction

Assess whether a candidate review distinguishes paper-reported claims from independently verified results, cites this
packet, preserves the registered numeric fact, states material limitations, and proposes an actionable next experiment.
