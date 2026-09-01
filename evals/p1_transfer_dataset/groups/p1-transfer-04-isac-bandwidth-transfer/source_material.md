# Synthetic Transfer Packet 04: Wideband ISAC detector to a narrowband sensing modem

1. This packet is repository-authored synthetic material.
2. The source solution uses a joint wideband sensing and communication detector.
3. Its reusable interface is documented, but deployment scripts are environment-specific.
4. The source evaluation does not include the target hardware or radio context.
5. Direct reuse is therefore not established by the source evidence.
6. The candidate adaptation is to redesign the waveform front end and recalibrate sensing thresholds.
7. Component-level reuse remains conditional on target-side validation.
8. No target performance point estimate is available.
9. The target context is a narrowband industrial sensing modem.
10. The registered target bandwidth limit is 20 MHz.
11. The target uses a different runtime or signal configuration from the source solution.
12. Compatibility must be measured rather than inferred from the source benchmark.
13. A failed constraint check blocks deployment but does not invalidate the source method.
14. Recommended validation is to measure detection probability and link error rate across the target band.
15. Legal, licensing, and operational approval remain outside this synthetic packet.
