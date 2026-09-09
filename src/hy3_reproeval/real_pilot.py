"""Deterministic real-paper pilot built from attributed open-access evidence."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import Field
from pypdf import PdfReader

from .errors import EvaluationInputError
from .models import StrictModel

REAL_PILOT_DATASET_ID = "reproeval-real-paper-pilot"
REAL_PILOT_DATASET_VERSION = "0.2.0"
REAL_PILOT_GROUP_COUNT = 6
REAL_PILOT_REPORT_COUNT = 18


@dataclass(frozen=True, slots=True)
class _Paper:
    slug: str
    title: str
    authors: str
    year: int
    doi: str
    paper_sha256: str
    repository_url: str
    archive_doi: str
    split: Literal["development", "validation", "test"]
    difficulty: Literal["standard", "hard"]
    primary_claim: str
    supporting_claims: tuple[str, str, str, str]
    numeric_label: str
    numeric_value: str
    corrupted_value: str
    numeric_unit: str | None
    primary_evidence_id: str
    numeric_evidence_id: str
    limitation_evidence_id: str
    limitation: str
    validation_action: str

    @property
    def paper_url(self) -> str:
        return f"https://joss.theoj.org/papers/10.21105/joss.{self.doi.rsplit('.', 1)[-1]}.pdf"

    @property
    def archive_url(self) -> str:
        return f"https://doi.org/{self.archive_doi}"

    @property
    def citation(self) -> str:
        return f"{self.authors} ({self.year}). {self.title}. Journal of Open Source Software. {self.doi}."


_PAPERS = (
    _Paper(
        slug="opticommpy",
        title="OptiCommPy: Open-source Simulation of Fiber Optic Communications with Python",
        authors="da Silva and Herbster",
        year=2024,
        doi="10.21105/joss.06600",
        paper_sha256="146FF130EB0B8DF3E2C6F8232AE889367D83CC148DA8269FE09D1714EFB6DD3E",
        repository_url="https://github.com/edsonportosilva/OptiCommPy",
        archive_doi="10.5281/zenodo.11450597",
        split="development",
        difficulty="standard",
        primary_claim=(
            "OptiCommPy is an open-source Python toolbox for physical-layer optical communication simulation."
        ),
        supporting_claims=(
            "The package covers digital modulation, channel and device models, receiver DSP, utilities, and plotting.",
            "The paper lists BER, SER, EVM, MI, GMI, and related metrics for transmission analysis.",
            "A documented getting-started example is described as reproducing the curves shown in Figure 2.",
            "The repository includes examples for nonlinear propagation, WDM transmission, and coherent detection.",
        ),
        numeric_label="The documented top-level package contains ",
        numeric_value="5",
        corrupted_value="8",
        numeric_unit="subpackages",
        primary_evidence_id="E01",
        numeric_evidence_id="E02",
        limitation_evidence_id="E04",
        limitation=(
            "The paper describes reproducible examples, but this pilot has not checked numerical agreement with "
            "Figure 2 or GPU benchmark values."
        ),
        validation_action=(
            "run the archived Figure 2 example in a pinned environment and compare exported BER and Q-factor curves "
            "with the paper"
        ),
    ),
    _Paper(
        slug="pyngham",
        title="PyNGHam: A Python library of the NGHam protocol",
        authors="Marcelino",
        year=2023,
        doi="10.21105/joss.04915",
        paper_sha256="25556A7620C512197DF4C3C22FEE2657DD885670025C9A26D92C1025D94F31D4",
        repository_url="https://github.com/mgm8/pyngham",
        archive_doi="10.5281/zenodo.7555428",
        split="development",
        difficulty="standard",
        primary_claim="PyNGHam provides a Python implementation of the NGHam amateur-radio packet protocol.",
        supporting_claims=(
            "The protocol uses Reed-Solomon forward error correction for wireless packets.",
            "The paper describes seven size-tag options with different Reed-Solomon configurations.",
            "The implementation exposes object-oriented support for normal packets, serial packets, and extensions.",
            "The reported use cases include CubeSat ground software, simulation, research, and education.",
        ),
        numeric_label="The largest documented payload is ",
        numeric_value="220",
        corrupted_value="512",
        numeric_unit="bytes",
        primary_evidence_id="E01",
        numeric_evidence_id="E04",
        limitation_evidence_id="E05",
        limitation=(
            "The paper documents protocol structure and deployments, but the pilot has not performed cross-language "
            "conformance or noisy-channel tests."
        ),
        validation_action=(
            "compare archived Python encoder and decoder outputs against the original C implementation for all seven "
            "packet sizes and controlled symbol errors"
        ),
    ),
    _Paper(
        slug="differt2d",
        title="DiffeRT2d: A Differentiable Ray Tracing Python Framework for Radio Propagation",
        authors="Eertmans, Oestges, and Jacques",
        year=2024,
        doi="10.21105/joss.06915",
        paper_sha256="E47AD55BFAC6021A3C25D93363D1BBECBBC0DD3FCB561F5923EA79D86450B384",
        repository_url="https://github.com/jeertmans/DiffeRT2d",
        archive_doi="10.5281/zenodo.12600658",
        split="validation",
        difficulty="hard",
        primary_claim="DiffeRT2d is a two-dimensional differentiable ray tracer for radio-propagation research.",
        supporting_claims=(
            "The implementation uses JAX and supports gradient-based optimization workflows.",
            "The paper discusses image, path-minimization, and Min-Path-Tracing methods.",
            "Its received-power calculation is explicitly described as a rough approximation that ignores local phase.",
            "The paper supplies code intended to reproduce the RIS coverage map in Figure 2.",
        ),
        numeric_label="The Figure 2 script configures ",
        numeric_value="1000",
        corrupted_value="10",
        numeric_unit="minimization steps",
        primary_evidence_id="E01",
        numeric_evidence_id="E04",
        limitation_evidence_id="E03",
        limitation=(
            "A visually similar coverage map would not by itself validate electromagnetic fidelity because the stated "
            "model omits local phase and does not compute full electromagnetic fields."
        ),
        validation_action=(
            "execute the archived v0.3.4 Figure 2 script, preserve environment metadata, compare the generated map, "
            "and keep physical-fidelity claims within the paper's approximation boundary"
        ),
    ),
    _Paper(
        slug="lyceanem",
        title=(
            "LyceanEM: A python package for virtual prototyping of antenna arrays, time and frequency domain "
            "channel modelling"
        ),
        authors="Pelham",
        year=2023,
        doi="10.21105/joss.05234",
        paper_sha256="8BD8D0C9CA6F701D1CB6AEC0312BBEFA11BBE063302605B3D1192089ABB6F539",
        repository_url="https://github.com/LyceanEM/LyceanEM-Python",
        archive_doi="10.5281/zenodo.8026567",
        split="validation",
        difficulty="hard",
        primary_claim="LyceanEM supports virtual prototyping of antennas, arrays, and propagation channels.",
        supporting_claims=(
            "The paper describes both frequency-domain and time-domain electromagnetic models.",
            "The implementation uses ray tracing and Numba-based CUDA acceleration for core calculations.",
            "The paper compares simulated scattering parameters with measurements from a metallic plate experiment.",
            "It also describes generation of channel-model data for machine-learning research.",
        ),
        numeric_label="The frequency-domain comparison uses measurements at ",
        numeric_value="26",
        corrupted_value="60",
        numeric_unit="GHz",
        primary_evidence_id="E01",
        numeric_evidence_id="E04",
        limitation_evidence_id="E04",
        limitation=(
            "The paper presents measured-versus-simulated plots, but this pilot has neither the raw measurement files "
            "nor an independent rerun of the simulation."
        ),
        validation_action=(
            "identify the archived script and raw measurement inputs for the scattering comparison, then compare the "
            "frequency- and time-domain outputs under a pinned CUDA and package environment"
        ),
    ),
    _Paper(
        slug="itmlogic",
        title="itmlogic: The Irregular Terrain Model by Longley and Rice",
        authors="Oughton, Russell, Johnson, Yardim, and Kusuma",
        year=2020,
        doi="10.21105/joss.02266",
        paper_sha256="5840DAF288A56B46C3253E9E392BA35A1E9E08D3F6DE11E808C693F9E8B379C4",
        repository_url="https://github.com/edwardoughton/itmlogic",
        archive_doi="10.5281/zenodo.3931350",
        split="test",
        difficulty="hard",
        primary_claim="itmlogic implements the Longley-Rice irregular-terrain propagation model in Python.",
        supporting_claims=(
            "The model predicts statistics of propagation loss from radio, climate, and terrain inputs.",
            "The paper distinguishes area-prediction and point-to-point operating modes.",
            "Input conventions mix metres for heights and kilometres for ranges within an MKS-oriented interface.",
            "Median loss estimates can feed wider link-budget and infrastructure analyses.",
        ),
        numeric_label="Point-to-point mode accepts up to ",
        numeric_value="600",
        corrupted_value="6000",
        numeric_unit="terrain-profile points",
        primary_evidence_id="E01",
        numeric_evidence_id="E04",
        limitation_evidence_id="E04",
        limitation=(
            "A Python implementation claim does not establish numerical equivalence to the reference Fortran or C++ "
            "implementations across propagation regimes."
        ),
        validation_action=(
            "run archived cross-implementation fixtures over area and point-to-point modes, including unit-boundary "
            "cases, and report numerical tolerances"
        ),
    ),
    _Paper(
        slug="cdcam",
        title="cdcam: Cambridge Digital Communications Assessment Model",
        authors="Oughton and Russell",
        year=2020,
        doi="10.21105/joss.01911",
        paper_sha256="1C06C332582C3D824B1BDD00BD40726975B5B5C0A3C59915A0D473F3DE2035D6",
        repository_url="https://github.com/nismod/cdcam",
        archive_doi="10.5281/zenodo.3583132",
        split="test",
        difficulty="hard",
        primary_claim="cdcam evaluates engineering and cost strategies for spatial 4G and 5G deployment.",
        supporting_claims=(
            "The model represents technology rollout over space and time under population and traffic scenarios.",
            "The paper distinguishes site points, lower-layer polygons, and upper-layer polygons.",
            "Strategies can vary spectral efficiency, spectrum holdings, and site density.",
            "A simulated capacity lookup table is described for multiple frequency bands and inter-site distances.",
        ),
        numeric_label="The capacity lookup range starts at ",
        numeric_value="400",
        corrupted_value="4000",
        numeric_unit="m",
        primary_evidence_id="E01",
        numeric_evidence_id="E05",
        limitation_evidence_id="E01",
        limitation=(
            "The paper describes national and subregional use, but policy conclusions depend on external population, "
            "traffic, cost, and deployment assumptions that are not reproduced in this pilot."
        ),
        validation_action=(
            "run the archived model with one documented regional scenario, verify the capacity lookup inputs, and "
            "separate software reproducibility from policy validity"
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class _Evidence:
    evidence_id: str
    statement: str
    page: int
    section: str
    excerpt: str


_PAPER_EVIDENCE: dict[str, tuple[_Evidence, ...]] = {
    "opticommpy": (
        _Evidence(
            "E01",
            "OptiCommPy is presented as an open-source alternative for optical-communication education and research.",
            2,
            "OptiCommPy code structure",
            (
                "OptiCommPy is intended to be an open-source alternative simulation tool for educational and "
                "research purposes."
            ),
        ),
        _Evidence(
            "E02",
            "The optic package has five top-level subpackages: comm, models, dsp, utils, and plot.",
            2,
            "OptiCommPy code structure",
            "the package is named optic, containing five sub-packages: comm, models, dsp, utils, and plot.",
        ),
        _Evidence(
            "E03",
            "The comm.metrics module includes BER, SER, EVM, MI, and GMI transmission metrics.",
            2,
            "OptiCommPy code structure",
            (
                "metrics, such as bit-error-rate (BER), symbol-error-rate (SER), error vector magnitude (EVM), "
                "mutual information (MI), and generalized mutual information (GMI)"
            ),
        ),
        _Evidence(
            "E04",
            "The documentation describes a getting-started example intended to reproduce the Figure 2 curves.",
            3,
            "Examples of usage",
            (
                "a getting started example that demonstrates some of the core features of OptiCommPy and "
                "reproduces the curves displayed in Fig. 2."
            ),
        ),
        _Evidence(
            "E05",
            "The repository is reported to include advanced simulation examples and GPU speedup benchmarks.",
            3,
            "Examples of usage",
            "Benchmarks quantifying the speedup achieved by using GPU acceleration are also provided.",
        ),
    ),
    "pyngham": (
        _Evidence(
            "E01",
            "PyNGHam is a Python implementation of the original C NGHam protocol library.",
            1,
            "Summary",
            "The PyNGHam library is a Python implementation of the original NGHam protocol library written in C",
        ),
        _Evidence(
            "E02",
            "NGHam uses Reed-Solomon forward error correction on a defined packet structure.",
            2,
            "NGHam Protocol",
            "For the FEC algorithm, the Reed-Solomon code (RS) is employed",
        ),
        _Evidence(
            "E03",
            "The size-tag field has seven options corresponding to seven packet sizes.",
            2,
            "NGHam Protocol",
            "The size tag field has seven different options, each corresponding to a unique packet size",
        ),
        _Evidence(
            "E04",
            "The largest row in Table 1 permits 220 bytes of data with RS(255, 223).",
            2,
            "Table 1: NGHam packet sizes",
            "7 237, 39, 52 RS(255, 223) 220 bytes of data",
        ),
        _Evidence(
            "E05",
            "The Python implementation exposes classes for normal packets, serial packets, and extensions.",
            3,
            "The Python Implementation",
            (
                "a class for each of the three main possible uses of the protocol is available: the normal NGHam "
                "packets, the serial port packets, and the use of the extensions."
            ),
        ),
    ),
    "differt2d": (
        _Evidence(
            "E01",
            "DiffeRT2d is presented as an open-source two-dimensional differentiable ray tracer using JAX.",
            1,
            "Summary",
            "We present DiffeRT2d, a 2D Open Source differentiable ray tracer",
        ),
        _Evidence(
            "E02",
            "The framework supports image, path-minimization, and Min-Path-Tracing methods.",
            2,
            "Statement of Need",
            "path minimization based on Fermat's principle",
        ),
        _Evidence(
            "E03",
            "Its received-power model is a rough approximation that ignores local wave phase.",
            2,
            "Easy to Use Commitment",
            "a rough approximation of the received power, which ignores the local phase of the wave",
        ),
        _Evidence(
            "E04",
            "The Figure 2 reproduction code configures 1000 minimization steps.",
            4,
            "Usage Examples - Exploring Metasurfaces and More",
            'path_cls_kwargs={"steps": 1000}',
        ),
        _Evidence(
            "E05",
            "The authors state an aim of maintaining 100% code coverage, not a measured guarantee in this Pilot.",
            5,
            "Stability and releases",
            "we aim to maintain a code coverage metric of 100%.",
        ),
    ),
    "lyceanem": (
        _Evidence(
            "E01",
            "LyceanEM is presented for virtual prototyping of antennas, arrays, and propagation channels.",
            1,
            "Summary",
            "LyceanEM is a Python library for modelling electromagnetic propagation for sensors and communications.",
        ),
        _Evidence(
            "E02",
            "The package includes frequency-domain and time-domain models.",
            1,
            "Summary",
            "Frequency Domain and Time Domain models are included",
        ),
        _Evidence(
            "E03",
            "LyceanEM relies on Numba for CUDA acceleration of electromagnetic calculations.",
            1,
            "Summary",
            "LyceanEM relies upon the Numba package to provide CUDA acceleration of electromagnetics",
        ),
        _Evidence(
            "E04",
            "Figure 6 compares measured and predicted scattering at 26 GHz.",
            4,
            "Frequency & Time Domain Channel Modelling",
            "measured scattering at 26GHz",
        ),
        _Evidence(
            "E05",
            "The paper reports an RMS error of -69 dB for one frequency-domain scattering comparison.",
            3,
            "Frequency & Time Domain Channel Modelling",
            (
                "with a root mean square (RMS) error of -69dB between the predicted scattering parameters and "
                "the measured data."
            ),
        ),
    ),
    "itmlogic": (
        _Evidence(
            "E01",
            "itmlogic is described as a Python implementation of the Longley-Rice Irregular Terrain Model.",
            1,
            "Summary",
            (
                "This paper describes the itmlogic package, which provides a Python implementation of the "
                "Longley-Rice Irregular Terrain Model."
            ),
        ),
        _Evidence(
            "E02",
            "The model predicts propagation-loss statistics from radio, climate, and terrain inputs.",
            1,
            "Summary",
            "itmlogic is capable of predicting the the statistics of propagation loss",
        ),
        _Evidence(
            "E03",
            "Height inputs are in metres while ranges are in kilometres.",
            2,
            "Spatial Units",
            (
                "transmitter and receiver heights above the local terrain are specified in meters while ranges "
                "are specified in kilometers."
            ),
        ),
        _Evidence(
            "E04",
            "Point-to-point mode uses up to 600 terrain-profile points.",
            3,
            "Prediction modes",
            "Point-to-point mode uses a sample of up to 600 points from the terrain profile",
        ),
        _Evidence(
            "E05",
            "Median loss estimates may be consumed by wider link-budget and infrastructure assessments.",
            3,
            "Applications",
            (
                "The median propagation loss estimates produced by itmlogic can be used with other link budget "
                "estimation models"
            ),
        ),
    ),
    "cdcam": (
        _Evidence(
            "E01",
            "cdcam quantifies engineering performance and cost for spatial 4G and 5G deployment strategies.",
            1,
            "Summary",
            "cdcam models the performance of 4G and 5G technologies as they roll-out over space and time",
        ),
        _Evidence(
            "E02",
            "The model uses site points plus lower- and upper-layer polygons.",
            2,
            "Spatial Units",
            "Three types of spatial units are used in the model",
        ),
        _Evidence(
            "E03",
            "Capacity and coverage strategies vary spectral efficiency, spectrum, and site count.",
            2,
            "Technologies and Deployment Strategies",
            "improving the spectral efficiency; adding more spectrum; and building more sites.",
        ),
        _Evidence(
            "E04",
            "The paper lists 4G and 5G bands and a small-cell deployment option.",
            2,
            "Technologies and Deployment Strategies",
            (
                "adding more spectrum bands, for either 4G (0.8 and 2.6 GHz), or 5G (0.7, 3.5, 26 GHz); and "
                "building more sites"
            ),
        ),
        _Evidence(
            "E05",
            "The capacity lookup simulations cover inter-site distances from 400 m to 30 km.",
            3,
            "Cellular capacity estimation",
            "for inter-site distances ranging from 400m to 30km.",
        ),
    ),
}


class RealPilotBuildResult(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    dataset_id: str
    dataset_version: str
    output_dir: str
    group_count: int = Field(ge=REAL_PILOT_GROUP_COUNT)
    report_count: int = Field(ge=REAL_PILOT_REPORT_COUNT)
    open_access_group_count: int = Field(ge=REAL_PILOT_GROUP_COUNT)
    draft_reference_report_count: int = Field(ge=REAL_PILOT_GROUP_COUNT)
    wrote_files: bool
    verified_existing: bool


class RealSourceVerificationItem(StrictModel):
    group_id: str
    source_file: str
    paper_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    page_count: int = Field(ge=1)
    evidence_statement_count: int = Field(ge=1)


class RealSourceVerificationResult(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    dataset_id: str = REAL_PILOT_DATASET_ID
    dataset_version: str = REAL_PILOT_DATASET_VERSION
    verified: Literal[True] = True
    paper_count: int = Field(ge=REAL_PILOT_GROUP_COUNT)
    evidence_statement_count: int = Field(ge=1)
    items: list[RealSourceVerificationItem] = Field(min_length=REAL_PILOT_GROUP_COUNT)


def materialize_real_pilot(output_dir: str | Path, *, check: bool = False) -> RealPilotBuildResult:
    """Create or byte-verify the canonical real-paper pilot Dataset."""

    root = Path(output_dir).expanduser().resolve()
    expected = build_real_pilot_files()
    if check:
        _verify_inventory(root, expected)
    else:
        if root.exists() and not root.is_dir():
            raise EvaluationInputError(f"real-paper pilot output must be a directory: {root.as_posix()}")
        if root.exists() and any(root.iterdir()):
            raise EvaluationInputError("real-paper pilot output directory must be absent or empty")
        root.mkdir(parents=True, exist_ok=True)
        for relative_path, payload in expected.items():
            target = root / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
    return RealPilotBuildResult(
        dataset_id=REAL_PILOT_DATASET_ID,
        dataset_version=REAL_PILOT_DATASET_VERSION,
        output_dir=root.as_posix(),
        group_count=REAL_PILOT_GROUP_COUNT,
        report_count=REAL_PILOT_REPORT_COUNT,
        open_access_group_count=REAL_PILOT_GROUP_COUNT,
        draft_reference_report_count=REAL_PILOT_GROUP_COUNT,
        wrote_files=not check,
        verified_existing=check,
    )


def verify_real_pilot_source_cache(source_dir: str | Path) -> RealSourceVerificationResult:
    """Verify cached PDFs and every registered evidence excerpt against its declared page."""

    root = Path(source_dir).expanduser().resolve()
    if not root.is_dir():
        raise EvaluationInputError(f"real-paper source cache does not exist: {root.as_posix()}")
    items: list[RealSourceVerificationItem] = []
    for index, paper in enumerate(_PAPERS, start=1):
        path = root / f"{paper.slug}.pdf"
        if not path.is_file():
            raise EvaluationInputError(f"real-paper source PDF is missing: {path.as_posix()}")
        payload = path.read_bytes()
        actual_sha256 = _sha256(payload)
        if actual_sha256 != paper.paper_sha256:
            raise EvaluationInputError(f"real-paper source PDF SHA-256 differs for '{paper.slug}'")
        try:
            reader = PdfReader(path)
        except Exception as exc:
            raise EvaluationInputError(f"real-paper source PDF cannot be parsed: {path.as_posix()}") from exc
        for evidence in _PAPER_EVIDENCE[paper.slug]:
            if evidence.page > len(reader.pages):
                raise EvaluationInputError(
                    f"evidence {paper.slug}/{evidence.evidence_id} references missing PDF page {evidence.page}"
                )
            page_text = reader.pages[evidence.page - 1].extract_text() or ""
            if _normalise_pdf_text(evidence.excerpt) not in _normalise_pdf_text(page_text):
                raise EvaluationInputError(
                    f"evidence excerpt {paper.slug}/{evidence.evidence_id} was not found on PDF page {evidence.page}"
                )
        items.append(
            RealSourceVerificationItem(
                group_id=f"real-paper-{index:02d}-{paper.slug}",
                source_file=path.name,
                paper_sha256=actual_sha256,
                page_count=len(reader.pages),
                evidence_statement_count=len(_PAPER_EVIDENCE[paper.slug]),
            )
        )
    return RealSourceVerificationResult(
        paper_count=len(items),
        evidence_statement_count=sum(item.evidence_statement_count for item in items),
        items=items,
    )


def build_real_pilot_files() -> dict[str, bytes]:
    """Return the canonical real-paper pilot inventory without filesystem access."""

    files: dict[str, bytes] = {}
    groups: list[dict[str, object]] = []
    for index, paper in enumerate(_PAPERS, start=1):
        group_id = f"real-paper-{index:02d}-{paper.slug}"
        group_root = f"groups/{group_id}"
        source = _source_material(paper)
        source_sha256 = _sha256(source)
        files[f"{group_root}/source_material.md"] = source
        source_assets = _source_assets(paper, group_root, source_sha256)
        source_group_sha256 = _canonical_sha256(source_assets)

        high = _high_report(paper)
        medium_operations = _medium_operations(paper)
        medium = _apply_operations(high.decode(), medium_operations).encode()
        low_operations = [*medium_operations, _corrupt_numeric_claim(paper)]
        low = _apply_operations(high.decode(), low_operations).encode()
        reports: list[dict[str, object]] = []
        for tier, payload, operations, label_source in (
            ("high", high, [], "curator_draft"),
            ("medium", medium, medium_operations, "synthetic_mutation"),
            ("low", low, low_operations, "synthetic_mutation"),
        ):
            report_name = f"{tier}_report.md"
            case_name = f"{tier}_case.json"
            report_id = f"{group_id}-{tier}"
            files[f"{group_root}/{report_name}"] = payload
            files[f"{group_root}/{case_name}"] = _json_bytes(_case(paper, group_id, tier, report_name, source_sha256))
            entry: dict[str, object] = {
                "report_id": report_id,
                "quality_tier": tier,
                "case_path": f"{group_root}/{case_name}",
                "report_sha256": _sha256(payload),
                "label_source": label_source,
                "expected_error_codes": (
                    []
                    if tier == "high"
                    else ["reasoning_gap", "actionability_gap"]
                    if tier == "medium"
                    else [
                        "reasoning_gap",
                        "actionability_gap",
                        "fabricated_citation",
                        "unsupported_claim",
                        "numeric_error",
                    ]
                ),
            }
            if operations:
                mutation_name = f"{tier}_mutation.json"
                entry["mutation_manifest_path"] = f"{group_root}/{mutation_name}"
                files[f"{group_root}/{mutation_name}"] = _json_bytes(
                    _mutation(group_id, tier, high, payload, operations)
                )
            reports.append(entry)

        groups.append(
            {
                "group_id": group_id,
                "split": paper.split,
                "scenario": "reproduction",
                "study_mode": "reproducibility_readiness",
                "difficulty": paper.difficulty,
                "provenance": {
                    "kind": "open_access",
                    "license": "CC-BY-4.0",
                    "source_group_sha256": source_group_sha256,
                    "acquisition_date": "2026-09-07",
                    "description": (
                        "ReproEval-authored evidence packet paraphrased from an attributed JOSS paper and its "
                        "software links; the external software was not executed."
                    ),
                    "citation": paper.citation,
                    "paper_url": paper.paper_url,
                    "repository_url": paper.repository_url,
                    "archive_url": paper.archive_url,
                    "paper_sha256": paper.paper_sha256,
                    "redistribution_policy": (
                        "The JOSS paper is CC BY 4.0. This repository stores an attributed paraphrased evidence "
                        "packet, not the downloaded PDF or third-party software."
                    ),
                    "source_assets": source_assets,
                },
                "reports": reports,
            }
        )

    files["dataset.json"] = _json_bytes(
        {
            "schema_version": "1.2",
            "dataset_id": REAL_PILOT_DATASET_ID,
            "dataset_version": REAL_PILOT_DATASET_VERSION,
            "description": (
                "Six-group open-access real-paper pilot for reproducibility-readiness evaluation. Source packets "
                "are grounded in CC BY JOSS papers and archived software metadata. No third-party code was executed; "
                "quality tiers remain curator-draft hypotheses until blinded human annotation is complete."
            ),
            "groups": groups,
        }
    )
    return files


def _source_material(paper: _Paper) -> bytes:
    evidence_blocks = "\n\n".join(
        (
            f"### {item.evidence_id}\n\n"
            f"- Curated statement: {item.statement}\n"
            f"- Paper locator: page {item.page}, section `{item.section}`.\n"
            f'- Short verification excerpt: "{item.excerpt}"'
        )
        for item in _PAPER_EVIDENCE[paper.slug]
    )
    text = f"""# Real Open-Access Evidence Packet: {paper.title}

## Provenance and scope

1. Source type: real open-access research software paper.
2. Citation: {paper.citation}
3. Paper DOI: {paper.doi}.
4. Paper PDF: {paper.paper_url}
5. Downloaded PDF SHA-256 on 2026-09-07: {paper.paper_sha256}.
6. Paper license: Creative Commons Attribution 4.0 International.
7. Software repository: {paper.repository_url}
8. Publication software archive: {paper.archive_url}
9. The evidence packet was acquired and curated on 2026-09-07.
10. This packet paraphrases selected paper claims and does not redistribute the PDF or source repository.
11. Study mode is reproducibility-readiness review; ReproEval has not executed the software.

## Verified paper evidence

The following statements were checked against the PDF identified above. Each statement carries a stable evidence ID,
PDF page, section label, and a short excerpt. Candidate reports must cite these IDs rather than inventing page ranges.

{evidence_blocks}

## Reproducibility evidence

- The journal record identifies reviewers and a persistent DOI.
- The journal record links a public software repository.
- The journal record links a publication-time software archive with a persistent DOI.
- The paper describes executable software features or examples relevant to its central claim.

## Limits of this Pilot case

- ReproEval did not install or execute the archived software for this Dataset version.
- No independent result table, runtime log, or environment lock was produced by ReproEval for this case.
- Therefore the case can assess reproducibility readiness, not successful numerical reproduction.
- Curator boundary: {paper.limitation}
- Registered next experiment: {paper.validation_action}.

## Evaluation instruction

Assess whether a candidate review distinguishes paper-reported claims from independently verified results, cites this
packet, preserves the registered numeric fact, states material limitations, and proposes an actionable next experiment.
"""
    return text.encode()


def _source_assets(
    paper: _Paper,
    group_root: str,
    evidence_sha256: str,
) -> list[dict[str, object]]:
    common = {
        "acquisition_date": "2026-09-07",
    }
    return [
        {
            "source_id": "paper-pdf",
            "kind": "paper_pdf",
            "media_type": "application/pdf",
            "license": "CC-BY-4.0",
            "description": "Published JOSS paper reviewed for the evidence register.",
            "uri": paper.paper_url,
            "sha256": paper.paper_sha256,
            **common,
        },
        {
            "source_id": "journal-record",
            "kind": "journal_record",
            "media_type": "text/html",
            "license": "CC-BY-4.0",
            "description": "JOSS publication page containing citation, review, license, and software links.",
            "uri": f"https://joss.theoj.org/papers/{paper.doi}",
            **common,
        },
        {
            "source_id": "software-repository",
            "kind": "software_repository",
            "media_type": "text/html",
            "license": "not-evaluated",
            "description": "Moving public repository referenced by the journal record; not executed by ReproEval.",
            "uri": paper.repository_url,
            **common,
        },
        {
            "source_id": "software-archive",
            "kind": "software_archive",
            "media_type": "text/html",
            "license": "not-evaluated",
            "description": "Persistent publication-time software archive referenced by the journal record.",
            "uri": paper.archive_url,
            **common,
        },
        {
            "source_id": "evidence-packet",
            "kind": "evidence_packet",
            "media_type": "text/markdown",
            "license": "Apache-2.0 with attributed CC-BY-4.0 excerpts",
            "description": "Repository-local evidence register derived from the reviewed paper PDF.",
            "local_path": f"{group_root}/source_material.md",
            "sha256": evidence_sha256,
            "derived_from": ["paper-pdf", "journal-record"],
            **common,
        },
    ]


def _high_report(paper: _Paper) -> bytes:
    unit = f" {paper.numeric_unit}" if paper.numeric_unit else ""
    text = f"""# Reproducibility-Readiness Review: {paper.title}

## Executive summary

This case supports a reproducibility-readiness conclusion, not an independent reproduction result.

## Experimental evidence

The paper-backed claim is that {paper.primary_claim[0].lower() + paper.primary_claim[1:]} \
[evidence@{paper.primary_evidence_id}].

The registered numeric fact is {paper.numeric_value}{unit} [evidence@{paper.numeric_evidence_id}].

The source registry binds the reviewed PDF, public repository, and publication archive to immutable metadata.

## Evidence and limitations

ReproEval did not execute the archived software, so there is insufficient evidence to claim numerical reproduction.
{paper.limitation} [evidence@{paper.limitation_evidence_id}].

## Next steps

To test the central claim, {paper.validation_action}, recording the exact archive, dependencies, commands, outputs,
and comparison tolerance.
"""
    return text.encode()


def _case(
    paper: _Paper,
    group_id: str,
    tier: str,
    report_name: str,
    source_sha256: str,
) -> dict[str, object]:
    numeric: dict[str, object] = {
        "fact_id": f"{paper.slug}-registered-fact",
        "label": "The registered numeric fact is",
        "expected": paper.numeric_value,
        "absolute_tolerance": "0",
        "critical": True,
    }
    if paper.numeric_unit:
        numeric["unit"] = paper.numeric_unit
    return {
        "schema_version": "1.0",
        "case_id": f"{group_id}-{tier}-case",
        "scenario": "reproduction",
        "report_path": report_name,
        "sources": [
            {
                "source_id": "evidence",
                "locators": [item.evidence_id for item in _PAPER_EVIDENCE[paper.slug]],
            }
        ],
        "claims": [
            {
                "claim_id": f"{paper.slug}-paper-claim",
                "marker": "The paper-backed claim is",
                "required_source_ids": ["evidence"],
            },
            {
                "claim_id": f"{paper.slug}-numeric-claim",
                "marker": "The registered numeric fact is",
                "required_source_ids": ["evidence"],
            },
        ],
        "numeric_expectations": [numeric],
        "required_sections": [
            {"section_id": "summary", "heading": "Executive summary"},
            {"section_id": "evidence", "heading": "Experimental evidence"},
            {"section_id": "limitations", "heading": "Evidence and limitations"},
            {"section_id": "next", "heading": "Next steps"},
        ],
        "uncertainty": {"required": True, "accepted_phrases": ["insufficient evidence"]},
        "artifacts": [{"artifact_id": f"{paper.slug}-source", "path": "source_material.md", "sha256": source_sha256}],
    }


def _medium_operations(paper: _Paper) -> list[dict[str, object]]:
    return [
        {
            "operation_id": "weaken-evidence-boundary",
            "kind": "replace_once",
            "target": (
                "ReproEval did not execute the archived software, so there is insufficient evidence to claim "
                "numerical reproduction."
            ),
            "replacement": "There is insufficient evidence, but the paper appears reproducible.",
            "expected_dimensions": ["reasoning_consistency"],
            "expected_error_codes": ["reasoning_gap"],
        },
        {
            "operation_id": "weaken-next-step",
            "kind": "replace_once",
            "target": (
                f"To test the central claim, {paper.validation_action}, recording the exact archive, dependencies, "
                "commands, outputs,\nand comparison tolerance."
            ),
            "replacement": "Run the software and inspect the results.",
            "expected_dimensions": ["clarity_actionability"],
            "expected_error_codes": ["actionability_gap"],
        },
    ]


def _corrupt_numeric_claim(paper: _Paper) -> dict[str, object]:
    unit = f" {paper.numeric_unit}" if paper.numeric_unit else ""
    return {
        "operation_id": "corrupt-registered-fact",
        "kind": "replace_once",
        "target": (
            f"The registered numeric fact is {paper.numeric_value}{unit} [evidence@{paper.numeric_evidence_id}]."
        ),
        "replacement": (f"The registered numeric fact is {paper.corrupted_value}{unit} [invented-authority@Table-1]."),
        "expected_dimensions": ["factual_accuracy", "evidence_traceability", "numerical_consistency"],
        "expected_error_codes": ["fabricated_citation", "unsupported_claim", "numeric_error"],
    }


def _mutation(
    group_id: str,
    tier: str,
    parent: bytes,
    output: bytes,
    operations: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "mutation_id": f"{group_id}-{tier}-mutation",
        "parent_report_id": f"{group_id}-high",
        "output_report_id": f"{group_id}-{tier}",
        "parent_path": f"groups/{group_id}/high_report.md",
        "output_path": f"groups/{group_id}/{tier}_report.md",
        "parent_sha256": _sha256(parent),
        "output_sha256": _sha256(output),
        "operations": operations,
    }


def _apply_operations(text: str, operations: list[dict[str, object]]) -> str:
    current = text
    for operation in operations:
        target = str(operation["target"])
        if current.count(target) != 1:
            raise RuntimeError(f"real-paper pilot mutation target is not unique: {operation['operation_id']}")
        current = current.replace(target, str(operation["replacement"]), 1)
    return current


def _verify_inventory(root: Path, expected: dict[str, bytes]) -> None:
    if not root.is_dir():
        raise EvaluationInputError(f"real-paper pilot directory does not exist: {root.as_posix()}")
    actual_paths = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    expected_paths = set(expected)
    if actual_paths != expected_paths:
        raise EvaluationInputError("real-paper pilot inventory differs from canonical generation")
    changed = [relative for relative, payload in expected.items() if (root / relative).read_bytes() != payload]
    if changed:
        raise EvaluationInputError("real-paper pilot files differ from canonical generation: " + ", ".join(changed))


def _json_bytes(payload: object) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode()


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()


def _canonical_sha256(payload: object) -> str:
    canonical = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return _sha256(canonical.encode())


def _normalise_pdf_text(value: str) -> str:
    normalised = unicodedata.normalize("NFKC", value)
    normalised = normalised.replace("\u2019", "'").replace("\u2018", "'")
    normalised = re.sub(r"-\s+", "-", normalised)
    return re.sub(r"\s+", " ", normalised).strip().casefold()
