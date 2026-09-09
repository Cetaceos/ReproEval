# Real-Paper Reproducibility-Readiness Pilot

`evals/real_paper_pilot` is ReproEval's first evaluation set grounded in real open-access research papers. It
contains six Journal of Open Source Software papers in communications, propagation, antennas, and physical-layer
simulation. Every paper is published under CC BY 4.0 and links to a public software repository and a
publication-time software archive.

## What the Pilot establishes

The Pilot tests whether ReproEval can evaluate reports about real, heterogeneous scientific software claims. It
does not claim that ReproEval reproduced the papers. No third-party package was installed or executed, and no
independent result table was produced. Every group therefore declares
`study_mode=reproducibility_readiness`.

The repository stores attributed evidence registers rather than downloaded PDFs or third-party source code. Each
register contains five stable evidence IDs with a curated statement, PDF page, section, and short verification
excerpt. Dataset 1.2 binds the reviewed PDF by URL and SHA-256, records the repository and archived release, hashes
the local register, and records its derivation from the paper and journal record. Downloaded review copies remain
outside version control.

## Inventory

| Split | Paper | Domain | Difficulty |
| --- | --- | --- | --- |
| development | OptiCommPy | optical communication simulation | standard |
| development | PyNGHam | amateur-radio packet protocol | standard |
| validation | DiffeRT2d | differentiable radio ray tracing | hard |
| validation | LyceanEM | antenna and channel modelling | hard |
| test | itmlogic | irregular-terrain propagation | hard |
| test | cdcam | spatial 4G/5G strategy modelling | hard |

Each group includes one source packet and high, medium, and low candidate reports. Medium and low reports are
reproducible Mutations of the high report. The high report is marked `curator_draft`, not `human_reviewed` or
`reference_revision`. Tier labels are hypotheses until independent blind annotation is complete.

## Build and validate

```bash
hy3-reproeval build-real-paper-pilot --output evals/real_paper_pilot --check
hy3-reproeval validate-dataset --manifest evals/real_paper_pilot/dataset.json
```

Expected inventory: six open-access groups, 18 reports, 12 Mutation Manifests, four hard groups, and balanced
2/2/2 splits. The 0.2.0 source layer contains 30 assets and 30 page-checked evidence statements. Validation must
report six curator drafts, zero human-reviewed report labels, and zero completed result-reproduction groups.

## Verify downloaded papers

Download each paper from its registered `paper_url` into a private directory using the filename shown below. Then
verify both the PDF bytes and all registered excerpts:

```text
opticommpy.pdf  pyngham.pdf  differt2d.pdf  lyceanem.pdf  itmlogic.pdf  cdcam.pdf
```

```bash
hy3-reproeval verify-real-paper-sources --source-dir .reproeval/source_cache
```

The command fails if a PDF is missing, a hash differs, a page does not exist, or an excerpt cannot be found on its
declared page. It does not execute the associated software.

## Generate Hy3 reference candidates

The committed high reports remain curator drafts. Generate fresh model candidates into a private, ignored directory:

```bash
hy3-reproeval generate-real-paper-references \
  --manifest evals/real_paper_pilot/dataset.json \
  --output-dir .reproeval/real-paper-reference-candidates
```

Each group receives `candidate.md`, an immutable `generation_record.json`, and a mutable `review_form.json` whose
initial status is `pending`. The record binds model/provider metadata, prompt version, Dataset, Case, source packet,
structured response, and rendered candidate with SHA-256 values.

A real reviewer checks the candidate against the registered PDF and evidence packet, then completes the form. Verify
all lineage while allowing pending decisions, or require all six explicit approvals:

```bash
hy3-reproeval validate-reference-reviews \
  --manifest evals/real_paper_pilot/dataset.json \
  --bundle-dir .reproeval/real-paper-reference-candidates

hy3-reproeval validate-reference-reviews \
  --manifest evals/real_paper_pilot/dataset.json \
  --bundle-dir .reproeval/real-paper-reference-candidates \
  --require-approved
```

Automated tests exercise approval and tamper rejection with a fake client; those fixtures are not human reviews.

## Experiment status and remaining work

1. Complete: freeze Dataset `0.2.0` before model and human scoring.
2. Complete: run three online TokenHub `hy3` Judge trials for all 18 reports and publish the aggregate result bundle.
3. Complete: collect two independently randomized validation/test work packets covering all 12 target reports.
4. Complete: resolve all four queued disagreements through a parent-bound third-reviewer packet.
5. Complete: publish de-identified consensus and per-run system-human comparisons in
   `results/real_paper_human_consensus`.
6. Deferred research track: generated high-report candidates remain `pending` and outside Dataset `0.2.0`. Promoting
   them would require explicit source review, a new Dataset version, rebuilt Mutations, a new Freeze, and new Judge
   and human experiments. Passing validation or blind scoring of the existing reports does not promote them.

The development split may be used to refine prompts and Rubric interpretation. Validation and test labels must
remain hidden from the evaluator. Human scores are external reference evidence, not per-item inputs to Hy3.

## Source records

- [OptiCommPy](https://joss.theoj.org/papers/10.21105/joss.06600)
- [PyNGHam](https://joss.theoj.org/papers/10.21105/joss.04915)
- [DiffeRT2d](https://joss.theoj.org/papers/10.21105/joss.06915)
- [LyceanEM](https://joss.theoj.org/papers/10.21105/joss.05234)
- [itmlogic](https://joss.theoj.org/papers/10.21105/joss.02266)
- [cdcam](https://joss.theoj.org/papers/10.21105/joss.01911)

The paper license does not automatically determine the software license. ReproEval records publication and
software links separately and makes no legal or deployment conclusion.
