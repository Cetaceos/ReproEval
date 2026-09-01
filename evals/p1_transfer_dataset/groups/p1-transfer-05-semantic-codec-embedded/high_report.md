# Transfer Review: Cloud semantic codec to an embedded terminal

## Decision summary

The transfer decision is conditional because the proposed adaptation must fit the target latency budget of 40 ms [solution@L2-L8] [target@L9-L14].

## Compatibility evidence

The reusable source interface is documented, while the target runtime or signal configuration differs [solution@L2-L8] [target@L9-L14].

## Risks and limitations

There is insufficient evidence for a target performance point estimate; compatibility and deployment readiness require target-side measurements.

## Validation plan

First measure end-to-end latency, task accuracy, and energy on target hardware; reject deployment if the registered constraint or acceptance metric fails.
