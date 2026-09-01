# Transfer Review: Wideband ISAC detector to a narrowband sensing modem

## Decision summary

The transfer decision is conditional because the proposed adaptation must fit the target bandwidth limit of 20 MHz [solution@L2-L8] [target@L9-L14].

## Compatibility evidence

The reusable source interface is documented, while the target runtime or signal configuration differs [solution@L2-L8] [target@L9-L14].

## Risks and limitations

There is insufficient evidence for a target performance point estimate; compatibility and deployment readiness require target-side measurements.

## Validation plan

First measure detection probability and link error rate across the target band; reject deployment if the registered constraint or acceptance metric fails.
