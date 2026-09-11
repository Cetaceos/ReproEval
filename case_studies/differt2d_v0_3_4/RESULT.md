# DiffeRT2d Figure 2 Reproduction Result

## Registered result

The frozen DiffeRT2d v0.3.4 Figure 2 case was executed on 2026-09-09 and
classified as exact under experiment protocol 1.0.

| Field | Observed value |
| --- | --- |
| Python | CPython 3.11.8 |
| JAX / jaxlib | 0.4.28 / 0.4.28 |
| Backend | CPU |
| Entrypoint exit code | 0 |
| Measured runner duration | 30.160 seconds |
| Power-grid shape | 300 x 300 |
| Linear-power finite values | 90,000 / 90,000 |
| dB finite values | 87,635 / 90,000 |
| dB negative infinities | 2,365 |
| Generated/reference image shape | 1313 x 1710 x 4 |
| Pixel MAE / RMSE | 0.0 / 0.0 |
| Pixel identity | true |

The negative infinities are the direct result of applying log10 to 2,365
zero-valued linear-power cells; they are recorded rather than silently removed.

## Frozen environment and source

| Item | Recorded value |
| --- | --- |
| DiffeRT2d | 0.3.4 |
| JAX / jaxlib | 0.4.28 / 0.4.28 |
| NumPy | 2.0.0 |
| Upstream lockfile SHA-256 | 372759137EE67F16CA776D5BC960D7D9344DBB745D4AC47D16F345B3C396F97A |
| Figure 2 entrypoint SHA-256 | E9F5BDE138A6C64841E6970CCC28958A2B6B47F253216A69F18A439EF242F7A1 |
| Zenodo archive SHA-256 | F61FA9F76F3614449480BFF9314D9F1DB7FF9414C9BC526AEF0473ED4DA6BABE |

The JOSS paper is distributed under CC BY 4.0. The DiffeRT2d v0.3.4
software release is distributed under the MIT License. These are separate
publication and software license records, not a legal conclusion by ReproEval.

## Evidence

The portable evidence is in the evidence directory. Its manifest binds six
published files and the private source-run manifest by SHA-256. The flat
figure2_summary.csv is a derived view of the registered run values for
deterministic aggregation; metrics.json remains the detailed source. The reproduced
PNG has SHA-256
D9DA4C4DDBBEDAB3B8F009FE1CE6EA18989A9F885E784804CB5454BE2C88FCE1,
which is byte-identical to the image in the frozen publication archive.

The downloaded archive, extracted source, dedicated environment, numerical NPZ,
generated PDF, and local absolute paths are deliberately not committed.

## Interpretation limit

This result establishes that the archived Figure 2 program reproduced its
archived numerical shape and image artifact in the recorded environment. It
does not independently validate the entire paper, the physical correctness of
the propagation model, or agreement with real channel measurements.
