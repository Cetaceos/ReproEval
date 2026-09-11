# DiffeRT2d v0.3.4 Figure 2 Reproduction

This case upgrades the DiffeRT2d entry in the frozen real-paper Pilot from
reproducibility readiness to one narrowly scoped result-reproduction
experiment. It re-executes the Figure 2 program shipped in the publication
archive and captures numerical arrays, rendered figures, logs, environment
metadata, and a hash-bound run manifest.

The experiment does not validate all claims in the paper and does not compare
the simulator against physical channel measurements.

## Frozen source

The source of record is the Zenodo archive for DiffeRT2d v0.3.4:

- paper DOI: 10.21105/joss.06915
- software DOI: 10.5281/zenodo.12600658
- fixed entrypoint: papers/joss/plot_ris_power_map.py
- archive metadata and digests: source_manifest.json
- parameters, evidence, and outcome rules: experiment_protocol.json

Third-party archives, extracted source, environments, and raw runs belong
under .reproeval/ and are intentionally excluded from Git.

## 1. Inspect and prepare

Download DiffeRT2d-v0.3.4.zip from the URL in source_manifest.json, then run:

~~~powershell
$Case = "case_studies\differt2d_v0_3_4"
$Archive = ".reproeval\third_party\differt2d-v0.3.4\DiffeRT2d-v0.3.4.zip"

.\.venv\Scripts\python.exe "$Case\scripts\run_reproduction.py" inspect --archive $Archive --output ".reproeval\differt2d\archive-inspection.json"
.\.venv\Scripts\python.exe "$Case\scripts\run_reproduction.py" prepare --archive $Archive --destination ".reproeval\differt2d\prepared-source" --output ".reproeval\differt2d\source-preparation.json"
~~~

Both commands fail closed on an unexpected archive digest, unsafe ZIP path,
escaping symbolic link, changed entrypoint, or changed archived reference
image. The archive's two safe internal documentation/test symlinks are recorded
and skipped during Windows extraction.

## 2. Create the dedicated environment

The upstream release pins Python 3.11.8 and declares support through Python
3.12. ReproEval's Python 3.13 development environment is not used to execute
this case.

~~~powershell
conda create --prefix ".reproeval\envs\differt2d-v0.3.4" python=3.11.8 pip -y
$EnvPrefix = (Resolve-Path ".reproeval\envs\differt2d-v0.3.4").Path
$Source = Resolve-Path ".reproeval\differt2d\prepared-source\jeertmans-DiffeRT2d-744a27e"
Push-Location $Source
conda run --prefix $EnvPrefix python -m pip install -r requirements.lock
Pop-Location
~~~

Running pip from the prepared source is required because the upstream lockfile
contains an editable file:. entry.

## 3. Execute and verify

~~~powershell
$Python = Resolve-Path ".reproeval\envs\differt2d-v0.3.4\python.exe"
.\.venv\Scripts\python.exe "$Case\scripts\run_reproduction.py" run --archive $Archive --python $Python --output-root ".reproeval\differt2d\runs"
.\.venv\Scripts\python.exe "$Case\scripts\run_reproduction.py" verify --run-dir "<RUN_DIRECTORY_PRINTED_BY_THE_RUN_COMMAND>"
~~~

The runner accepts no arbitrary command. It verifies the exact source and
entrypoint, extracts into a new run directory, forwards no credential variables,
forces JAX CPU and Matplotlib Agg, applies a timeout, and records failures as
evidence. It does not claim OS-level network isolation on Windows.

## Evidence interpretation

exact means the generated PNG pixels match the archived PNG and all structural
gates pass. visually_consistent permits a declared normalized pixel mean
absolute error of at most 0.01. artifact_divergence means the official program
completed but its rendered result crossed that threshold.

These labels describe this fixed artifact experiment only. A successful run is
evidence that the archived Figure 2 workflow executes under the recorded
environment; it is not an independent scientific validation of the model.

## Publish a sanitized evidence bundle

After verify succeeds, export the portable subset:

~~~powershell
.\.venv\Scripts\python.exe "$Case\scripts\run_reproduction.py" export --run-dir "<RUN_DIRECTORY>" --output-dir "$Case\evidence"
.\.venv\Scripts\python.exe "$Case\scripts\run_reproduction.py" verify-public --evidence-dir "$Case\evidence"
~~~

The committed evidence bundle excludes the downloaded archive, extracted
third-party source, dedicated environment, absolute interpreter path, NPZ, and
PDF. It retains the environment versions, numerical summary, logs, reproduced
PNG, artifact hashes, and the original private run-manifest hash. The exported
figure2_summary.csv is a flat view derived from the verified metrics and run
duration so MCP clients can request deterministic numeric aggregation without
flattening nested JSON themselves.
