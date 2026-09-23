import csv
from pathlib import Path

import pytest

from uliana.development_baseline import (
    MANIFEST_HEADER,
    PREDICTION_FIELDS,
    ManifestValidationError,
    calculate_metrics,
    development_rows,
    validate_manifest,
    write_predictions,
)


ROOT = Path(__file__).parents[1]


def _copy_fixture(tmp_path: Path):
    source = ROOT / "data/incoming/recordings_manifest.csv"
    manifest = tmp_path / "manifest.csv"
    manifest.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    video_root = tmp_path / "recordings"
    video_root.mkdir()
    with manifest.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        (video_root / row["filename"]).touch()
    return manifest, video_root, rows


def _rewrite(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_HEADER)
        writer.writeheader()
        writer.writerows(rows)


def test_manifest_validation_and_manual_count_parsing(tmp_path):
    manifest, video_root, _ = _copy_fixture(tmp_path)
    rows, controls = validate_manifest(manifest, video_root)
    assert len(rows) == 30
    assert controls["development_repetitions"] == 116
    assert controls["holdout_repetitions"] == 51
    assert controls["total_repetitions"] == 167


def test_invalid_manual_count_fails_closed(tmp_path):
    manifest, video_root, rows = _copy_fixture(tmp_path)
    rows[0]["manual_repetition_count"] = "4.5"
    _rewrite(manifest, rows)
    with pytest.raises(ManifestValidationError, match="invalid manual repetition count"):
        validate_manifest(manifest, video_root)


def test_participant_level_split_isolation(tmp_path):
    manifest, video_root, rows = _copy_fixture(tmp_path)
    rows[0]["split"] = "holdout"
    _rewrite(manifest, rows)
    with pytest.raises(ManifestValidationError, match="multiple splits"):
        validate_manifest(manifest, video_root)


def test_development_selection_excludes_holdout(tmp_path):
    manifest, video_root, _ = _copy_fixture(tmp_path)
    rows, _ = validate_manifest(manifest, video_root)
    selected = development_rows(rows)
    assert len(selected) == 21
    assert {row["participant_id"] for row in selected} == {f"anon-p{number:03d}" for number in range(1, 8)}


def test_unavailable_predictions_reduce_coverage_without_becoming_zero():
    rows = [
        {
            "participant_id": "anon-p001",
            "session_id": "a",
            "manual_viewpoint": "side",
            "manual_repetition_count": "5",
            "predicted_viewpoint": "side",
            "viewpoint_confidence": ".9",
            "predicted_repetition_count": "5",
            "repetition_confidence": ".8",
            "pose_detection_coverage": ".9",
            "selected_phase_signal": "observable_elbow_angle",
            "processing_status": "success",
            "eligible_assessments": "2",
            "answered_assessments": "2",
            "unavailable_reasons": "",
            "quality_warnings": "",
        },
        {
            "participant_id": "anon-p001",
            "session_id": "b",
            "manual_viewpoint": "front",
            "manual_repetition_count": "4",
            "predicted_viewpoint": "unknown",
            "viewpoint_confidence": "",
            "predicted_repetition_count": "",
            "repetition_confidence": "",
            "pose_detection_coverage": ".2",
            "selected_phase_signal": "",
            "processing_status": "success",
            "eligible_assessments": "0",
            "answered_assessments": "0",
            "unavailable_reasons": "phase_signal_unavailable",
            "quality_warnings": "repetition_count_unavailable",
        },
    ]
    metrics = calculate_metrics(rows)
    count = metrics["repetition_count"]
    assert count["coverage"] == .5
    assert count["unavailable_predictions"] == 1
    assert count["count_mae"] == 0
    assert count["total_predicted_answered"] == 5
    assert count["total_manual_answered"] == 5
    assert count["total_manual_eligible"] == 9


def test_valid_zero_is_answered_and_distinct_from_unavailable():
    rows = [
        {"participant_id": "anon-p001", "session_id": "zero", "manual_viewpoint": "side",
         "manual_repetition_count": "1", "predicted_viewpoint": "side", "viewpoint_confidence": ".9",
         "predicted_repetition_count": "0", "repetition_confidence": ".7", "pose_detection_coverage": ".9",
         "selected_phase_signal": "observable_elbow_angle", "processing_status": "success",
         "eligible_assessments": "0", "answered_assessments": "0", "unavailable_reasons": "", "quality_warnings": ""},
        {"participant_id": "anon-p001", "session_id": "missing", "manual_viewpoint": "front",
         "manual_repetition_count": "1", "predicted_viewpoint": "unknown", "viewpoint_confidence": "",
         "predicted_repetition_count": "", "repetition_confidence": "", "pose_detection_coverage": ".1",
         "selected_phase_signal": "", "processing_status": "success", "eligible_assessments": "0",
         "answered_assessments": "0", "unavailable_reasons": "phase_signal_unavailable", "quality_warnings": ""},
    ]
    count = calculate_metrics(rows)["repetition_count"]
    assert count["coverage"] == .5
    assert count["answered_recordings"] == 1
    assert count["unavailable_predictions"] == 1
    assert count["total_predicted_answered"] == 0
    assert count["count_mae"] == 1


def test_metric_calculations():
    rows = []
    for participant, manual, predicted in (("anon-p001", 4, 3), ("anon-p002", 6, 8), ("anon-p003", 5, 5)):
        rows.append({
            "participant_id": participant,
            "session_id": participant,
            "manual_viewpoint": "side",
            "manual_repetition_count": str(manual),
            "predicted_viewpoint": "side",
            "viewpoint_confidence": ".8",
            "predicted_repetition_count": str(predicted),
            "repetition_confidence": ".7",
            "pose_detection_coverage": ".9",
            "selected_phase_signal": "observable_elbow_angle",
            "processing_status": "success",
            "eligible_assessments": "2",
            "answered_assessments": "1",
            "unavailable_reasons": "viewpoint_not_supported",
            "quality_warnings": "",
        })
    count = calculate_metrics(rows)["repetition_count"]
    assert count["count_mae"] == 1
    assert count["count_rmse"] == pytest.approx((5 / 3) ** .5)
    assert count["median_absolute_error"] == 1
    assert count["exact_count_accuracy"] == pytest.approx(1 / 3)
    assert count["within_one_accuracy"] == pytest.approx(2 / 3)
    assert count["mean_signed_error"] == pytest.approx(1 / 3)


def test_manual_fields_preserved_and_rerun_is_idempotent(tmp_path):
    manifest, video_root, _ = _copy_fixture(tmp_path)
    rows, _ = validate_manifest(manifest, video_root)
    selected = development_rows(rows)
    predictions = []
    for row in selected:
        output = {field: "" for field in PREDICTION_FIELDS}
        for field in ("filename", "participant_id", "session_id", "manual_viewpoint", "manual_repetition_count"):
            output[field] = row[field]
        output["processing_status"] = "failed"
        output["unavailable_reasons"] = "test"
        predictions.append(output)
    destination = tmp_path / "predictions.csv"
    write_predictions(destination, predictions)
    first = destination.read_bytes()
    write_predictions(destination, predictions)
    second = destination.read_bytes()
    assert first == second
    with destination.open(newline="", encoding="utf-8") as handle:
        saved = list(csv.DictReader(handle))
    assert len(saved) == 21
    for source, output in zip(selected, saved):
        for field in ("filename", "participant_id", "session_id", "manual_viewpoint", "manual_repetition_count"):
            assert output[field] == source[field]
