# Reproducibility-Readiness Review: LyceanEM: A python package for virtual prototyping of antenna arrays, time and frequency domain channel modelling

## Executive summary

This case supports a reproducibility-readiness conclusion, not an independent reproduction result.

## Experimental evidence

The paper-backed claim is that lyceanEM supports virtual prototyping of antennas, arrays, and propagation channels. [evidence@E01].

The registered numeric fact is 26 GHz [evidence@E04].

The source registry binds the reviewed PDF, public repository, and publication archive to immutable metadata.

## Evidence and limitations

ReproEval did not execute the archived software, so there is insufficient evidence to claim numerical reproduction.
The paper presents measured-versus-simulated plots, but this pilot has neither the raw measurement files nor an independent rerun of the simulation. [evidence@E04].

## Next steps

To test the central claim, identify the archived script and raw measurement inputs for the scattering comparison, then compare the frequency- and time-domain outputs under a pinned CUDA and package environment, recording the exact archive, dependencies, commands, outputs,
and comparison tolerance.
