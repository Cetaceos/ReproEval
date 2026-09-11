# DiffeRT2d v0.3.4 transfer source evidence

## Provenance

- Paper: Eertmans, Oestges, and Jacques (2024), "DiffeRT2d: A Differentiable Ray Tracing Python Framework for Radio Propagation."
- Journal and DOI: Journal of Open Source Software, 10.21105/joss.06915.
- Paper license: Creative Commons Attribution 4.0 International.
- Paper PDF SHA-256: `E47AD55BFAC6021A3C25D93363D1BBECBBC0DD3FCB561F5923EA79D86450B384`.
- Software repository: `https://github.com/jeertmans/DiffeRT2d`.
- Publication archive DOI: 10.5281/zenodo.12600658.
- Software version and license: DiffeRT2d v0.3.4, MIT.
- Archive SHA-256 observed on 2026-09-09: `F61FA9F76F3614449480BFF9314D9F1DB7FF9414C9BC526AEF0473ED4DA6BABE`.

## Paper-supported capabilities

The paper presents DiffeRT2d as an open-source, two-dimensional differentiable ray tracer implemented with JAX.
The described path methods include image-based tracing, Fermat-principle path minimization, and Min-Path-Tracing.
The Figure 2 configuration contains two reconfigurable intelligent surfaces and 1000 minimization steps.

The paper characterizes its received-power calculation as a rough approximation that omits local wave phase. This
boundary matters for coherent arrays, complex channel coefficients, delay, Doppler, and electromagnetic-fidelity
claims. The paper expresses 100% code coverage as a maintenance aim rather than a result established by this case.

## Independently recorded Figure 2 evidence

The publication-time v0.3.4 archive and its fixed Figure 2 entrypoint were evaluated on 2026-09-09. The recorded
environment used CPython 3.11.8, DiffeRT2d 0.3.4, JAX and jaxlib 0.4.28, NumPy 2.0.0, and a CPU backend. The process
finished with exit code 0 in 30.160 seconds.

The resulting power grid contained 300 by 300 cells. All 90,000 linear-power values were finite. Conversion to dB
produced 87,635 finite values and 2,365 negative infinities corresponding to zero-valued linear-power cells. The
generated and archived PNG arrays both had shape 1313 by 1710 by 4. Pixel MAE and RMSE were 0.0, and the image bytes
were identical with SHA-256 `D9DA4C4DDBBEDAB3B8F009FE1CE6EA18989A9F885E784804CB5454BE2C88FCE1`.

## Transfer boundary

The recorded result establishes reproduction of the archived Figure 2 software artifact in the recorded environment.
It does not establish reproduction of every paper claim, agreement with measured radio channels, three-dimensional
mobility support, complex-channel fidelity, or suitability for integrated sensing and communication.

Potentially reusable elements include the JAX computation model, differentiable path-search concepts, bounded scene
experimentation, and the publication archive's reproducible software structure. Three-dimensional geometry, moving
endpoints, arrays, coherent phase, propagation delay, Doppler, near-field behavior, sensing observations, and
measurement-backed calibration remain outside the evidence established by this source.

## Evidence records

- `source_manifest.json` records paper, repository, archive, release, entrypoint, lockfile, and reference-image identifiers.
- `experiment_protocol.json` records the fixed Figure 2 scope, parameters, environment policy, and outcome rules.
- `evidence/environment.json` records the observed software environment.
- `evidence/metrics.json` records the numerical grid and image-comparison statistics.
- `evidence/public_evidence_manifest.json` binds the public evidence files and source identifiers by SHA-256.
- `RESULT.md` states the registered result and its interpretation limit.
