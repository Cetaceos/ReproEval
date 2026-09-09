# Blinded Annotation Work Packets

ReproEval prepares one randomized packet per annotator as an operational bridge between a frozen Dataset and the
strict human Annotation Bundles defined in [ANNOTATION_PROTOCOL.md](ANNOTATION_PROTOCOL.md). Packet schema `1.1`
includes both candidate reports and registered source materials without exposing registered quality tiers, Mutation
metadata, expected errors, or system scores.

This workflow supports data collection; it does not create human labels, verify expert identity, or establish
scientific validity by itself.

## Packet boundary

Each packet root contains two trust domains:

```text
packet-reviewer-a/
  coordinator_manifest.json   private mapping and fingerprints; never send to the annotator
  annotator/
    assignment.json           public Rubric, instructions, scoring anchors, and neutral item inventory
    responses.json            editable annotation form
    reports/
      item-001.md              randomized, canonically numbered report copy
      ...
    sources/
      item-001-source-001.md   neutral, canonically numbered source copy
      ...
```

Only the `annotator/` directory is shared with the assigned reviewer. The coordinator keeps
`coordinator_manifest.json` private and restores the returned `annotator/` directory beneath the original packet
root before finalization. Separate annotators receive separately generated packets and must not see one another's
responses.

The generator includes validation and test reports only. Development reports are excluded from the human
benchmark-readiness target. Every source is a Dataset-registered artifact with a verified SHA-256. Public source IDs
(`source-001`, and so on) and filenames are neutral; the original artifact mapping remains only in the coordinator
manifest. Both reports and sources use immutable `L000001 | ...` line prefixes.

## 1. Freeze the Dataset

Create private working directories and freeze the exact registered inputs before preparing any assignment:

```bash
mkdir -p .reproeval private_annotations
hy3-reproeval freeze-dataset \
  --manifest evals/real_paper_pilot/dataset.json \
  --output .reproeval/real-paper-pilot-freeze.json
```

Use the same Freeze for every annotator, Judge run, Benchmark, agreement analysis, and consensus artifact in the
experiment.

## 2. Prepare independent packets

Generate a distinct packet for each pseudonymous annotator:

```bash
hy3-reproeval prepare-annotation-packet \
  --manifest evals/real_paper_pilot/dataset.json \
  --dataset-freeze .reproeval/real-paper-pilot-freeze.json \
  --output-dir private_annotations/real-pilot-reviewer-a \
  --assignment-id real-pilot-independent-a \
  --annotator-id reviewer-a \
  --bundle-id real-pilot-bundle-a
```

Repeat with different assignment, annotator, bundle, and output identifiers for reviewer B. Output directories
must be absent or empty. Random item order is generated independently for each packet.

## 3. Complete the response form

The reviewer edits only `annotator/responses.json`:

- complete `annotation_date` and every annotator-profile declaration;
- assess every one of the seven dimensions for every neutral item;
- for `assessed`, provide a score from 0 to 4, a rationale, and at least one valid report line;
- for assessed `factual_accuracy`, `evidence_traceability`, and `numerical_consistency`, also populate
  `source_evidence` with a neutral source ID and one or more valid source lines;
- for `insufficient_evidence`, leave `score` as `null` and explain the missing evidence;
- use only the dimension-specific error codes listed in `assignment.json`.

Line references may use either the integer part (`1`) or the displayed canonical identifier (`L000001`). Source
references accept `evidence_lines` and the human-friendly `lines` alias. Finalization converts both forms to strict
integer lists and preserves up to 16 cited lines per report or source reference. The assignment, report, and source
files must not be edited.

## 4. Verify and finalize

After restoring the returned `annotator/` directory under its private packet root, create the strict Bundle:

```bash
hy3-reproeval finalize-annotation-packet \
  --manifest evals/p1_transfer_dataset/dataset.json \
  --dataset-freeze .reproeval/p1-transfer-freeze.json \
  --packet-dir private_annotations/p1-reviewer-a \
  --output private_annotations/p1-reviewer-a.json
```

Finalization reconstructs every numbered copy from the frozen registered input. It fails if the Dataset, Freeze,
Rubric, assignment, report or source copy, private item/source mapping, profile, report/source evidence line, or
response contract does not match. Neutral source references are mapped back to registered artifact IDs in the
resulting `independent` human Annotation Bundle.

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

## 6. Prepare and finalize third-reviewer adjudication

When `analyze-annotations` emits queued disputes, generate a separate packet for a third reviewer:

```bash
hy3-reproeval prepare-adjudication-packet \
  --manifest evals/real_paper_pilot/dataset.json \
  --dataset-freeze .reproeval/real-paper-pilot-freeze.json \
  --bundle private_annotations/real-pilot-reviewer-a.json \
  --bundle private_annotations/real-pilot-reviewer-b.json \
  --output-dir private_annotations/real-pilot-adjudicator-c \
  --assignment-id real-pilot-adjudication-c \
  --adjudicator-id adjudicator-c \
  --bundle-id real-pilot-adjudication-bundle-c
```

The packet contains only reports and dimensions in the program-generated dispute queue. The third reviewer sees
the two parent assessments under randomized `parent-001`/`parent-002` aliases, including their evidence traces,
but does not see reviewer identities, parent Bundle IDs, quality tiers, Mutation metadata, or system scores. Only
the generated `annotator/` directory is shared.

The adjudicator fills only the dimensions present in `responses.json`, sets `independent_annotation=false` because
the parent assessments are intentionally visible, and remains blind to system scores. After return, finalize the
packet against the unchanged parent files:

```bash
hy3-reproeval finalize-adjudication-packet \
  --manifest evals/real_paper_pilot/dataset.json \
  --dataset-freeze .reproeval/real-paper-pilot-freeze.json \
  --bundle private_annotations/real-pilot-reviewer-a.json \
  --bundle private_annotations/real-pilot-reviewer-b.json \
  --packet-dir private_annotations/real-pilot-adjudicator-c \
  --output private_annotations/real-pilot-adjudication-c.json
```

The finalizer recomputes the dispute queue, reconstructs every numbered copy, verifies the anonymous parent
assessments, and binds both parent Bundle IDs and SHA-256 fingerprints into the adjudication Bundle. It rejects a
changed parent, a parent reviewer reused as adjudicator, an altered assignment or source, or a response outside the
queued dimensions. Submit both parent Bundles and the adjudication Bundle to `finalize-annotations`; only that
command determines whether consensus is complete.

## Security notes

- Keep packet roots, completed responses, Bundle files, and identity records outside version control.
- Never send `coordinator_manifest.json` to an annotator.
- Do not include API keys, direct personal identifiers, system scores, or Judge outputs in a work packet.
- Packet generation copies registered UTF-8 report and source text only; it does not execute Dataset content or call Hy3.
- The source hash in `assignment.json` authenticates the original registered bytes; the numbered-copy hash authenticates
  the exact file delivered to the reviewer.
- Treat self-attested profile declarations as research records, not verified credentials.
