# ReproEval documentation

This directory contains the current protocols, experiment reports, and delivery evidence. Start with the repository
[README](../README.md) or [Chinese README](../README_CN.md), then use this page to locate implementation details.

## Architecture and interfaces

- [Evaluation core](EVALUATION_CORE.md): versioned rubric, score semantics, and evaluator boundaries.
- [Skill adapter](SKILL_ADAPTER.md): the reusable Skill interface built on the evaluation core.
- [Dataset protocol](DATASET_PROTOCOL.md): source, mutation, split, and provenance requirements.
- [Benchmark protocol](BENCHMARK_PROTOCOL.md): benchmark execution and acceptance rules.
- [Result export](RESULT_EXPORT.md) and [figures](RESULT_FIGURES.md): reproducible public result bundles.

## Evaluation datasets and experiments

- [P0 dataset](P0_DATASET.md): synthetic reproduction-readiness and adversarial regression set.
- [P1 transfer dataset](P1_TRANSFER_DATASET.md): conditional solution-transfer evaluation set.
- [P1 Judge experiment](P1_JUDGE_EXPERIMENT_CN.md): three-run Hy3 results for the transfer set.
- [Real-paper pilot](REAL_PAPER_PILOT.md): six open-access JOSS source groups and the frozen dataset design.
- [Real-paper Judge experiment](REAL_PAPER_JUDGE_EXPERIMENT_CN.md): three-run Hy3 results on the real-source pilot.
- [Human validation](REAL_PAPER_HUMAN_VALIDATION_CN.md): blinded review, adjudication, and system-human comparison.
- [DiffeRT2d protocol](DIFFERT2D_REPRODUCTION_PROTOCOL_CN.md): executable Figure 2 reproduction protocol.

## Annotation and robustness

- [Annotation protocol](ANNOTATION_PROTOCOL.md) and [packet format](ANNOTATION_PACKET.md).
- [Dataset freeze](DATASET_FREEZE.md), [Judge batches](JUDGE_BATCH.md), and [stability](STABILITY_PROTOCOL.md).
- [Adversarial protocol](ADVERSARIAL_PROTOCOL.md) and [pairwise comparison](PAIRWISE_COMPARISON.md).
- [Reference generation review](REFERENCE_GENERATION_REVIEW_CN.md) and [pilot review guide](REAL_PILOT_REVIEW_GUIDE_CN.md).

## Delivery

- [Project proposal](PROJECT_PROPOSAL_CN.md).
- [Delivery status](DELIVERY_STATUS_CN.md).
- [WorkBuddy final demo guide](WORKBUDDY_FINAL_DEMO_CN.md).

## Historical material

The original ReproScope 0.15 evidence and migration notes are retained in
[`archive/reproscope-0.15`](archive/reproscope-0.15/README.md). They document project provenance but do not describe the
current ReproEval release.
