# Reproducibility-Readiness Review: DiffeRT2d: A Differentiable Ray Tracing Python Framework for Radio Propagation

## Executive summary

This case supports a reproducibility-readiness conclusion, not an independent reproduction result.

## Experimental evidence

The paper-backed claim is that diffeRT2d is a two-dimensional differentiable ray tracer for radio-propagation research. [evidence@E01].

The registered numeric fact is 1000 minimization steps [evidence@E04].

The source registry binds the reviewed PDF, public repository, and publication archive to immutable metadata.

## Evidence and limitations

ReproEval did not execute the archived software, so there is insufficient evidence to claim numerical reproduction.
A visually similar coverage map would not by itself validate electromagnetic fidelity because the stated model omits local phase and does not compute full electromagnetic fields. [evidence@E03].

## Next steps

To test the central claim, execute the archived v0.3.4 Figure 2 script, preserve environment metadata, compare the generated map, and keep physical-fidelity claims within the paper's approximation boundary, recording the exact archive, dependencies, commands, outputs,
and comparison tolerance.
