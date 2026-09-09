# Reproducibility-Readiness Review: itmlogic: The Irregular Terrain Model by Longley and Rice

## Executive summary

This case supports a reproducibility-readiness conclusion, not an independent reproduction result.

## Experimental evidence

The paper-backed claim is that itmlogic implements the Longley-Rice irregular-terrain propagation model in Python. [evidence@E01].

The registered numeric fact is 600 terrain-profile points [evidence@E04].

The source registry binds the reviewed PDF, public repository, and publication archive to immutable metadata.

## Evidence and limitations

ReproEval did not execute the archived software, so there is insufficient evidence to claim numerical reproduction.
A Python implementation claim does not establish numerical equivalence to the reference Fortran or C++ implementations across propagation regimes. [evidence@E04].

## Next steps

To test the central claim, run archived cross-implementation fixtures over area and point-to-point modes, including unit-boundary cases, and report numerical tolerances, recording the exact archive, dependencies, commands, outputs,
and comparison tolerance.
