# Reproducibility-Readiness Review: PyNGHam: A Python library of the NGHam protocol

## Executive summary

This case supports a reproducibility-readiness conclusion, not an independent reproduction result.

## Experimental evidence

The paper-backed claim is that pyNGHam provides a Python implementation of the NGHam amateur-radio packet protocol. [evidence@E01].

The registered numeric fact is 220 bytes [evidence@E04].

The source registry binds the reviewed PDF, public repository, and publication archive to immutable metadata.

## Evidence and limitations

ReproEval did not execute the archived software, so there is insufficient evidence to claim numerical reproduction.
The paper documents protocol structure and deployments, but the pilot has not performed cross-language conformance or noisy-channel tests. [evidence@E05].

## Next steps

To test the central claim, compare archived Python encoder and decoder outputs against the original C implementation for all seven packet sizes and controlled symbol errors, recording the exact archive, dependencies, commands, outputs,
and comparison tolerance.
