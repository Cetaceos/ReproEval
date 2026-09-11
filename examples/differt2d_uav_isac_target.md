# Proposed target context: DiffeRT2d for a three-dimensional UAV-BS ISAC research workflow

## Status and decision scope

This document defines a proposed research target for a conditional technology-transfer assessment. It is not an
implemented system, a measured benchmark, or evidence that DiffeRT2d already supports the target. The assessment
must not predict target-side performance without target measurements.

## Research objective

The target project studies a mobile UAV base station serving ground users while collecting sensing observations of
the surrounding scene. It needs a reproducible physical-layer simulation workflow for testing channel prediction,
beam prediction, and near-field versus far-field classification under controlled trajectories.

The intended use of DiffeRT2d is limited to evaluating whether its scene representation, differentiable path search,
and JAX-based computation can be reused as an early software component. The target does not assume that a
two-dimensional received-power map is an adequate three-dimensional ISAC channel model.

## Required physical-layer representation

1. Three-dimensional transmitter, receiver, reflector, and obstacle coordinates.
2. Time-indexed UAV trajectories and moving endpoints.
3. Multi-antenna links with complex channel coefficients, propagation delay, angle of arrival/departure, and Doppler.
4. Explicit carrier frequency, bandwidth, array geometry, transmit-power budget, and noise model.
5. Near-field and far-field propagation regimes with a documented transition criterion.
6. A common scene and resource configuration for communication and sensing evaluation.

The current target profile uses MIMO-OFDM as a candidate waveform, but waveform selection is not frozen and must not
be inferred from the DiffeRT2d Figure 2 reproduction.

## Evaluation requirements

Communication evaluation must report channel-prediction NMSE and at least one link metric such as spectral
efficiency, BER, or outage probability. Sensing evaluation must report task-appropriate quantities such as range or
angle RMSE, detection probability, and false-alarm probability. Every comparison must preserve or explicitly record
changes to bandwidth, power, noise, geometry, trajectory, seed, and aggregation rules.

The first feasibility milestone is a deterministic offline prototype, not a real-time deployment. It must run a
small canonical scene on CPU and may use one local GPU for larger experiments. Runtime, peak memory, numerical
stability, and dependency versions must be recorded rather than assumed.

## Available target resources

- Python 3.11 and a JAX-compatible development environment.
- Synthetic canonical scenes and programmable UAV trajectories.
- Existing channel-prediction and beam-prediction research code that can consume structured channel tensors.
- Engineering access to CPU and a single development GPU.

No calibrated over-the-air UAV-BS channel dataset, hardware-in-the-loop setup, or independently validated
three-dimensional propagation reference is currently available. These are material evidence gaps.

## Known transfer risks

- DiffeRT2d is a two-dimensional framework, while the target geometry is three-dimensional and mobile.
- The paper describes received power as a rough approximation that ignores local wave phase; this is insufficient
  for a target that requires complex channel coefficients, coherent arrays, Doppler, and delay.
- Pixel identity for the archived Figure 2 establishes software-artifact reproduction only. It does not establish
  physical accuracy against measured channels or suitability for ISAC.
- Differentiability and JAX reuse may be valuable, but component interfaces and computational scaling require
  direct inspection and measurement.
- Paper, software, dependencies, datasets, and generated artifacts require separate license and provenance checks.

## Acceptance gates

1. Produce a minimal three-dimensional scene and a documented mapping from DiffeRT2d concepts to target concepts.
2. Demonstrate deterministic repeated output under a frozen environment and seed.
3. Compare at least one canonical scene with an independent simulator or measurement-backed reference.
4. Verify complex-channel, delay, Doppler, and array outputs before connecting downstream learning tasks.
5. Run controlled communication and sensing evaluations without changing unreported resource budgets.
6. Record unsupported requirements and reject deployment claims when the required evidence is absent.

Until these gates are satisfied, the only admissible decision is conditional research reuse or prototype-only reuse,
not production readiness.
