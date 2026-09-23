import importlib.util
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("holdout_eval", ROOT / "scripts/run_holdout_evaluation.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_prediction_input_excludes_manual_labels_and_split():
    row = {"filename":"x.MOV", "participant_id":"anon-p008", "session_id":"s", "manual_viewpoint":"front", "manual_repetition_count":"9", "split":"holdout"}
    assert MODULE.prediction_input(row) == {"filename":"x.MOV", "participant_id":"anon-p008", "session_id":"s"}


def test_attaching_evaluation_labels_does_not_change_prediction():
    prediction = {"session_id":"s", "predicted_repetition_count":0, "predicted_viewpoint":"side"}
    output = MODULE.attach_evaluation(prediction, {"manual_viewpoint":"front", "manual_repetition_count":"9"})
    assert prediction == {"session_id":"s", "predicted_repetition_count":0, "predicted_viewpoint":"side"}
    assert output["predicted_repetition_count"] == 0
    assert output["manual_repetition_count"] == "9"


def test_freeze_verification_matches_before_media_access():
    args = SimpleNamespace(
        config=ROOT / "configs/video_processing.json",
        freeze_manifest=ROOT / "artifacts/real_recordings/development_baseline_v2/freeze_manifest.json",
        manifest=ROOT / "data/incoming/recordings_manifest.csv",
        model=ROOT / "models/pose_landmarker_full.task",
    )
    verified = MODULE.verify_freeze(args)
    assert verified["status"] == "matched"
    assert verified["checks"]["configuration_sha256"] == MODULE.FROZEN_CONFIG_SHA256
