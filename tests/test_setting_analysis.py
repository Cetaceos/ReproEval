from __future__ import annotations

from hy3_reproscope_mcp.config import Settings
from hy3_reproscope_mcp.loaders import load_sources
from hy3_reproscope_mcp.models import CompareReproductionResult
from hy3_reproscope_mcp.setting_analysis import build_setting_checks, reconcile_setting_differences


def _bundles(tmp_path, paper_text: str, reproduction_text: str, *, reproduction_name: str = "train.log"):
    paper_path = tmp_path / "paper.md"
    reproduction_path = tmp_path / reproduction_name
    paper_path.write_text(paper_text, encoding="utf-8")
    reproduction_path.write_text(reproduction_text, encoding="utf-8")
    settings = Settings(REPROSCOPE_ALLOWED_ROOTS=str(tmp_path))
    paper = load_sources(
        [str(paper_path)],
        role="paper",
        settings=settings,
        source_id_prefix="paper",
    )
    reproduction = load_sources(
        [str(reproduction_path)],
        role="reproduction",
        settings=settings,
        source_id_prefix="repro",
    )
    return paper, reproduction


def _comparison(setting_differences=None) -> CompareReproductionResult:
    return CompareReproductionResult.model_validate(
        {
            "run_id": "compare_test",
            "summary": "Setting comparison.",
            "setting_differences": setting_differences or [],
            "conclusion_stability": "Depends on deterministic setting checks.",
        }
    )


def test_common_text_settings_match_after_normalization(tmp_path) -> None:
    paper, reproduction = _bundles(
        tmp_path,
        (
            "Training uses 100 epochs, optimizer is AdamW, learning rate 3e-4, "
            "batch size 32, weight decay 0.01, and scheduler cosine."
        ),
        ("epochs=100 optimizer=adamw learning_rate=0.0003 batch_size=32 weight_decay=1e-2 scheduler=Cosine"),
    )

    checks = build_setting_checks(paper, reproduction)

    assert {check.setting: check.status.value for check in checks} == {
        "epochs": "match",
        "learning_rate": "match",
        "batch_size": "match",
        "optimizer": "match",
        "weight_decay": "match",
        "scheduler": "match",
    }
    assert all(check.paper_citations for check in checks)
    assert all(check.reproduction_citations for check in checks)


def test_epoch_phrase_does_not_capture_learning_rate_fraction(tmp_path) -> None:
    paper, reproduction = _bundles(
        tmp_path,
        "Training uses learning rate 0.0003 for 100 epochs.",
        "learning_rate=0.0003 epochs=100",
    )

    checks = {check.setting: check for check in build_setting_checks(paper, reproduction)}

    assert checks["epochs"].status.value == "match"
    assert checks["epochs"].reproduction_values == ["100"]
    assert checks["learning_rate"].status.value == "match"


def test_deterministic_mismatch_replaces_model_proposed_setting_difference(tmp_path) -> None:
    paper, reproduction = _bundles(
        tmp_path,
        "The model is trained for 100 epochs.",
        "epochs=50",
    )
    result = _comparison(
        [
            {
                "setting": "training epochs",
                "paper_value": "100",
                "reproduction_value": "75",
                "severity": "minor",
                "likely_effect": "Model-proposed explanation.",
            },
            {
                "setting": "CUDA version",
                "paper_value": "12.1",
                "reproduction_value": "11.8",
                "severity": "minor",
                "likely_effect": "Potential environment effect.",
            },
        ]
    )

    checks = build_setting_checks(paper, reproduction)
    reconcile_setting_differences(result, checks)

    epochs = next(difference for difference in result.setting_differences if difference.setting == "epochs")
    assert epochs.paper_value == "100"
    assert epochs.reproduction_value == "50"
    assert epochs.severity.value == "critical"
    assert epochs.citations
    assert any(difference.setting == "CUDA version" for difference in result.setting_differences)
    assert any(warning.code == "DETERMINISTIC_SETTING_MISMATCH" for warning in result.warnings)
    assert any(warning.code == "SETTING_DIFFERENCES_RECALCULATED" for warning in result.warnings)


def test_local_match_removes_false_model_difference(tmp_path) -> None:
    paper, reproduction = _bundles(
        tmp_path,
        "Training uses optimizer AdamW for 100 epochs.",
        "optimizer=adamw epochs=100",
    )
    result = _comparison(
        [
            {
                "setting": "optimizer",
                "paper_value": "AdamW",
                "reproduction_value": "SGD",
                "severity": "critical",
                "likely_effect": "The optimizer differs.",
            }
        ]
    )

    reconcile_setting_differences(result, build_setting_checks(paper, reproduction))

    assert result.setting_differences == []
    assert any(warning.code == "SETTING_DIFFERENCES_RECALCULATED" for warning in result.warnings)


def test_ambiguous_reproduction_setting_abstains_from_difference(tmp_path) -> None:
    paper, reproduction = _bundles(
        tmp_path,
        "Training uses 100 epochs.",
        "run_1 epochs=50\nrun_2 epochs=60\n",
    )
    result = _comparison(
        [
            {
                "setting": "epochs",
                "paper_value": "100",
                "reproduction_value": "50",
                "severity": "critical",
                "likely_effect": "The training budget differs.",
            }
        ]
    )

    reconcile_setting_differences(result, build_setting_checks(paper, reproduction))

    assert result.deterministic_setting_checks[0].status.value == "ambiguous"
    assert result.setting_differences == []
    assert any(warning.code == "AMBIGUOUS_EXPERIMENT_SETTING" for warning in result.warnings)
    assert any("Which epochs value" in question for question in result.unresolved_questions)


def test_structured_config_settings_are_preserved_and_checked(tmp_path) -> None:
    paper, reproduction = _bundles(
        tmp_path,
        "The optimizer is AdamW and batch size is 64.",
        '{"config":{"optimizer":"adamw","batch_size":64},"results":[{"accuracy":0.8}]}',
        reproduction_name="results.json",
    )

    checks = build_setting_checks(paper, reproduction)

    assert {check.setting: check.status.value for check in checks} == {
        "batch_size": "match",
        "optimizer": "match",
    }


def test_seed_count_phrase_is_not_treated_as_an_explicit_seed_value(tmp_path) -> None:
    paper, reproduction = _bundles(
        tmp_path,
        "The paper reports results using five random seeds.",
        "seed,accuracy\n1,0.8\n2,0.9\n",
        reproduction_name="results.csv",
    )

    seed_check = next(check for check in build_setting_checks(paper, reproduction) if check.setting == "seed")

    assert seed_check.status.value == "missing_in_paper"
    assert seed_check.paper_values == []
    assert set(seed_check.reproduction_values) == {"1", "2"}
