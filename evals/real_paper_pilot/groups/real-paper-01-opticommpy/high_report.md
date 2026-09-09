# Reproducibility-Readiness Review: OptiCommPy: Open-source Simulation of Fiber Optic Communications with Python

## Executive summary

This case supports a reproducibility-readiness conclusion, not an independent reproduction result.

## Experimental evidence

The paper-backed claim is that optiCommPy is an open-source Python toolbox for physical-layer optical communication simulation. [evidence@E01].

The registered numeric fact is 5 subpackages [evidence@E02].

The source registry binds the reviewed PDF, public repository, and publication archive to immutable metadata.

## Evidence and limitations

ReproEval did not execute the archived software, so there is insufficient evidence to claim numerical reproduction.
The paper describes reproducible examples, but this pilot has not checked numerical agreement with Figure 2 or GPU benchmark values. [evidence@E04].

## Next steps

To test the central claim, run the archived Figure 2 example in a pinned environment and compare exported BER and Q-factor curves with the paper, recording the exact archive, dependencies, commands, outputs,
and comparison tolerance.
