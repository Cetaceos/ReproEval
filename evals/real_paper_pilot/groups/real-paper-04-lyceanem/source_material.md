# Real Open-Access Evidence Packet: LyceanEM: A python package for virtual prototyping of antenna arrays, time and frequency domain channel modelling

## Provenance and scope

1. Source type: real open-access research software paper.
2. Citation: Pelham (2023). LyceanEM: A python package for virtual prototyping of antenna arrays, time and frequency domain channel modelling. Journal of Open Source Software. 10.21105/joss.05234.
3. Paper DOI: 10.21105/joss.05234.
4. Paper PDF: https://joss.theoj.org/papers/10.21105/joss.05234.pdf
5. Downloaded PDF SHA-256 on 2026-09-07: 8BD8D0C9CA6F701D1CB6AEC0312BBEFA11BBE063302605B3D1192089ABB6F539.
6. Paper license: Creative Commons Attribution 4.0 International.
7. Software repository: https://github.com/LyceanEM/LyceanEM-Python
8. Publication software archive: https://doi.org/10.5281/zenodo.8026567
9. The evidence packet was acquired and curated on 2026-09-07.
10. This packet paraphrases selected paper claims and does not redistribute the PDF or source repository.
11. Study mode is reproducibility-readiness review; ReproEval has not executed the software.

## Verified paper evidence

The following statements were checked against the PDF identified above. Each statement carries a stable evidence ID,
PDF page, section label, and a short excerpt. Candidate reports must cite these IDs rather than inventing page ranges.

### E01

- Curated statement: LyceanEM is presented for virtual prototyping of antennas, arrays, and propagation channels.
- Paper locator: page 1, section `Summary`.
- Short verification excerpt: "LyceanEM is a Python library for modelling electromagnetic propagation for sensors and communications."

### E02

- Curated statement: The package includes frequency-domain and time-domain models.
- Paper locator: page 1, section `Summary`.
- Short verification excerpt: "Frequency Domain and Time Domain models are included"

### E03

- Curated statement: LyceanEM relies on Numba for CUDA acceleration of electromagnetic calculations.
- Paper locator: page 1, section `Summary`.
- Short verification excerpt: "LyceanEM relies upon the Numba package to provide CUDA acceleration of electromagnetics"

### E04

- Curated statement: Figure 6 compares measured and predicted scattering at 26 GHz.
- Paper locator: page 4, section `Frequency & Time Domain Channel Modelling`.
- Short verification excerpt: "measured scattering at 26GHz"

### E05

- Curated statement: The paper reports an RMS error of -69 dB for one frequency-domain scattering comparison.
- Paper locator: page 3, section `Frequency & Time Domain Channel Modelling`.
- Short verification excerpt: "with a root mean square (RMS) error of -69dB between the predicted scattering parameters and the measured data."

## Reproducibility evidence

- The journal record identifies reviewers and a persistent DOI.
- The journal record links a public software repository.
- The journal record links a publication-time software archive with a persistent DOI.
- The paper describes executable software features or examples relevant to its central claim.

## Limits of this Pilot case

- ReproEval did not install or execute the archived software for this Dataset version.
- No independent result table, runtime log, or environment lock was produced by ReproEval for this case.
- Therefore the case can assess reproducibility readiness, not successful numerical reproduction.
- Curator boundary: The paper presents measured-versus-simulated plots, but this pilot has neither the raw measurement files nor an independent rerun of the simulation.
- Registered next experiment: identify the archived script and raw measurement inputs for the scattering comparison, then compare the frequency- and time-domain outputs under a pinned CUDA and package environment.

## Evaluation instruction

Assess whether a candidate review distinguishes paper-reported claims from independently verified results, cites this
packet, preserves the registered numeric fact, states material limitations, and proposes an actionable next experiment.
