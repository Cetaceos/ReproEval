from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import runpy
import shutil
import sys
from pathlib import Path
from typing import Any

CASE_ID = "differt2d-v0.3.4-figure2"
ENTRYPOINT = Path("papers/joss/plot_ris_power_map.py")
ENTRYPOINT_SHA256 = "E9F5BDE138A6C64841E6970CCC28958A2B6B47F253216A69F18A439EF242F7A1"
EXPECTED_PACKAGES = {
    "DiffeRT2d": "0.3.4",
    "beartype": "0.18.5",
    "differt-core": "0.0.17",
    "equinox": "0.11.4",
    "jax": "0.4.28",
    "jaxlib": "0.4.28",
    "jaxtyping": "0.2.28",
    "matplotlib": "3.8.4",
    "numpy": "2.0.0",
    "optax": "0.2.2",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def collect_environment() -> dict[str, Any]:
    versions: dict[str, str | None] = {}
    for package in EXPECTED_PACKAGES:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None

    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "case_id": CASE_ID,
        "python": {
            "executable": sys.executable,
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "supported_by_protocol": sys.version_info[:2] in {(3, 11), (3, 12)},
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "packages": versions,
        "fixed_environment": {
            "JAX_PLATFORM_NAME": os.environ.get("JAX_PLATFORM_NAME"),
            "MPLBACKEND": os.environ.get("MPLBACKEND"),
            "PYTHONNOUSERSITE": os.environ.get("PYTHONNOUSERSITE"),
            "XLA_PYTHON_CLIENT_PREALLOCATE": os.environ.get("XLA_PYTHON_CLIENT_PREALLOCATE"),
        },
        "jax": {"backend": None, "devices": [], "probe_error": None},
    }
    try:
        import jax

        payload["jax"] = {
            "backend": jax.default_backend(),
            "devices": [str(device) for device in jax.devices()],
            "probe_error": None,
        }
    except Exception as exc:  # pragma: no cover - depends on the external environment
        payload["jax"]["probe_error"] = f"{type(exc).__name__}: {exc}"
    return payload


def _array_summary(array: Any) -> dict[str, Any]:
    import numpy as np

    values = np.asarray(array)
    finite = np.isfinite(values)
    finite_values = values[finite]
    summary: dict[str, Any] = {
        "shape": list(values.shape),
        "dtype": str(values.dtype),
        "element_count": int(values.size),
        "finite_count": int(finite.sum()),
        "finite_ratio": float(finite.mean()) if values.size else 0.0,
        "nan_count": int(np.isnan(values).sum()),
        "positive_infinity_count": int(np.isposinf(values).sum()),
        "negative_infinity_count": int(np.isneginf(values).sum()),
    }
    if finite_values.size:
        summary.update(
            min=float(finite_values.min()),
            max=float(finite_values.max()),
            mean=float(finite_values.mean()),
            std=float(finite_values.std()),
            quantiles={
                "q01": float(np.quantile(finite_values, 0.01)),
                "q50": float(np.quantile(finite_values, 0.50)),
                "q99": float(np.quantile(finite_values, 0.99)),
            },
        )
    return summary


def _compare_images(generated: Path, reference: Path) -> dict[str, Any]:
    import matplotlib.image as mpimg
    import numpy as np

    actual = np.asarray(mpimg.imread(generated), dtype=np.float64)
    expected = np.asarray(mpimg.imread(reference), dtype=np.float64)
    result: dict[str, Any] = {
        "generated_shape": list(actual.shape),
        "reference_shape": list(expected.shape),
        "shape_matches": actual.shape == expected.shape,
        "pixel_exact": False,
        "normalized_mean_absolute_error": None,
        "normalized_root_mean_squared_error": None,
        "visual_threshold": 0.01,
    }
    if actual.shape != expected.shape:
        return result
    difference = actual - expected
    result.update(
        pixel_exact=bool(np.array_equal(actual, expected)),
        normalized_mean_absolute_error=float(np.mean(np.abs(difference))),
        normalized_root_mean_squared_error=float(np.sqrt(np.mean(difference**2))),
    )
    return result


def execute(source_root: Path, evidence_dir: Path, reference_image: Path) -> None:
    import numpy as np

    source_root = source_root.resolve()
    evidence_dir = evidence_dir.resolve()
    script = (source_root / ENTRYPOINT).resolve()
    if not script.is_relative_to(source_root) or _sha256(script) != ENTRYPOINT_SHA256:
        raise RuntimeError("the fixed DiffeRT2d Figure 2 entrypoint failed its SHA-256 check")

    environment = collect_environment()
    _write_json(evidence_dir / "environment.json", environment)
    if not environment["python"]["supported_by_protocol"]:
        raise RuntimeError("DiffeRT2d execution requires the dedicated Python 3.11 or 3.12 environment")
    if environment["jax"]["backend"] != "cpu":
        raise RuntimeError("the DiffeRT2d case must run on the declared JAX CPU backend")
    mismatches = {
        name: {"expected": expected, "actual": environment["packages"][name]}
        for name, expected in EXPECTED_PACKAGES.items()
        if environment["packages"][name] != expected
    }
    if mismatches:
        raise RuntimeError(f"the dedicated environment does not match the upstream lock: {mismatches}")

    sys.path.insert(0, str(source_root))
    previous_cwd = Path.cwd()
    try:
        os.chdir(script.parent)
        namespace = runpy.run_path(str(script), run_name="__differt2d_figure2__")
    finally:
        os.chdir(previous_cwd)

    power = np.asarray(namespace["P"])
    power_db = np.asarray(namespace["PdB"])
    generated_png = script.parent / "static" / "ris_power_map.png"
    generated_pdf = script.parent / "ris_power_map.pdf"
    if not generated_png.is_file() or not generated_pdf.is_file():
        raise RuntimeError("the official entrypoint did not create both declared figure artifacts")

    artifacts = evidence_dir / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(artifacts / "figure2_arrays.npz", power=power, power_db=power_db)
    shutil.copy2(generated_png, artifacts / "ris_power_map.png")
    shutil.copy2(generated_pdf, artifacts / "ris_power_map.pdf")
    shutil.copy2(reference_image, artifacts / "reference_ris_power_map.png")

    image_comparison = _compare_images(
        artifacts / "ris_power_map.png",
        artifacts / "reference_ris_power_map.png",
    )
    metrics = {
        "schema_version": "1.0",
        "case_id": CASE_ID,
        "entrypoint": ENTRYPOINT.as_posix(),
        "entrypoint_sha256": ENTRYPOINT_SHA256,
        "grid": {
            "x": _array_summary(namespace["X"]),
            "y": _array_summary(namespace["Y"]),
        },
        "power_linear": _array_summary(power),
        "power_db": _array_summary(power_db),
        "image_comparison": image_comparison,
    }
    _write_json(evidence_dir / "metrics.json", metrics)


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture evidence from the fixed DiffeRT2d Figure 2 entrypoint.")
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    parser.add_argument("--reference-image", required=True, type=Path)
    args = parser.parse_args()
    execute(args.source_root, args.evidence_dir, args.reference_image)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
