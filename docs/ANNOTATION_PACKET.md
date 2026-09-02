# Blinded Annotation Work Packets

ReproEval 0.32.0 adds an operational bridge between a frozen Dataset and the strict human Annotation Bundles
defined in [ANNOTATION_PROTOCOL.md](ANNOTATION_PROTOCOL.md). It prepares one randomized packet per annotator
without exposing registered quality tiers, mutation metadata, expected errors, or system scores.

This workflow supports data collection; it does not create human labels, verify expert identity, or establish
scientific validity by itself.

## Packet boundary

Each packet root contains two trust domains:

```text
packet-reviewer-a/
  coordinator_manifest.json   private mapping and fingerprints; never send to the annotator
  annotator/
    assignment.json           public Rubric, instructions, and neutral item inventory
    responses.json            editable annotation form
    reports/
      item-001.md              randomized neutral report copies
      ...
```

Only the `annotator/` directory is shared with the assigned reviewer. The coordinator keeps
`coordinator_manifest.json` private and restores the returned `annotator/` directory beneath the original packet
root before finalization. Separate annotators receive separately generated packets and must not see one another's
responses.

The generator includes validation and test reports only. Development reports are excluded from the human
benchmark-readiness target.

## 1. Freeze the Dataset

Create private working directories and freeze the exact registered inputs before preparing any assignment:

```bash
mkdir -p .reproeval private_annotations
hy3-reproeval freeze-dataset \
  --manifest evals/p1_transfer_dataset/dataset.json \
  --output .reproeval/p1-transfer-freeze.json
```

Use the same Freeze for every annotator, Judge run, Benchmark, agreement analysis, and consensus artifact in the
experiment.

## 2. Prepare independent packets

Generate a distinct packet for each pseudonymous annotator:

```bash
hy3-reproeval prepare-annotation-packet \
  --manifest evals/p1_transfer_dataset/dataset.json \
  --dataset-freeze .reproeval/p1-transfer-freeze.json \
  --output-dir private_annotations/p1-reviewer-a \
  --assignment-id p1-independent-a \
  --annotator-id reviewer-a \
  --bundle-id p1-independent-bundle-a
```

Repeat with different assignment, annotator, bundle, and output identifiers for reviewer B. Output directories
must be absent or empty. Random item order is generated independently for each packet.

## 3. Complete the response form

The reviewer edits only `annotator/responses.json`:

- complete `annotation_date` and every annotator-profile declaration;
- assess every one of the seven dimensions for every neutral item;
- for `assessed`, provide a score from 0 to 4, a rationale, and at least one valid report line;
- for `insufficient_evidence`, leave `score` as `null` and explain the missing evidence;
- use only the dimension-specific error codes listed in `assignment.json`.

Line numbers start at 1 in the copied report. The assignment and report files must not be edited.

## 4. Verify and finalize

After restoring the returned `annotator/` directory under its private packet root, create the strict Bundle:

```bash
hy3-reproeval finalize-annotation-packet \
  --manifest evals/p1_transfer_dataset/dataset.json \
  --dataset-freeze .reproeval/p1-transfer-freeze.json \
  --packet-dir private_annotations/p1-reviewer-a \
  --output private_annotations/p1-reviewer-a.json
```

Finalization fails if the Dataset, Freeze, Rubric, assignment, report copy, item inventory, profile, evidence line,
or response contract does not match. The output is an `independent` human Annotation Bundle accepted by the
existing validation, agreement, and consensus commands.

## 5. Validate coverage

Once two independent Bundles are available:

```bash
hy3-reproeval validate-annotations \
  --manifest evals/p1_transfer_dataset/dataset.json \
  --dataset-freeze .reproeval/p1-transfer-freeze.json \
  --bundle private_annotations/p1-reviewer-a.json \
  --bundle private_annotations/p1-reviewer-b.json \
  --output .reproeval/p1-annotation-validation.json
```

`benchmark_ready=true` means every validation/test report has two structurally eligible independent human
annotations. It does not prove that annotators were qualified, remained blind in practice, or produced correct
labels. Use agreement analysis and independent adjudication before reporting a consensus result.

## Security notes

- Keep packet roots, completed responses, Bundle files, and identity records outside version control.
- Never send `coordinator_manifest.json` to an annotator.
- Do not include API keys, direct personal identifiers, system scores, or Judge outputs in a work packet.
- Packet generation copies registered report text only; it does not execute Dataset content or call Hy3.
- Treat self-attested profile declarations as research records, not verified credentials.
