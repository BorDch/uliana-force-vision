import json
from scripts.review_overlay import review_moments


def fixture(tmp_path, visibility=1, result="condition_detected", side="left"):
    folder = tmp_path / "session"
    analysis = folder / "analysis"
    analysis.mkdir(parents=True)
    (analysis / "session_result.json").write_text(json.dumps({
        "provenance": {"experimental_configuration": {"landmark_quality": {"minimum_visibility": .65, "minimum_presence": .65}}},
        "assessments": [{"rep_id": 1, "condition": "body_alignment_deviation", "result": result,
                         "evidence": {"maximum_normalized_hip_displacement": .3,
                                      "experimental_thresholds": {"normalized_hip_displacement": .08, "angle_deviation_deg": 8}}}]}))
    (analysis / "video_summary.json").write_text(json.dumps({"observable_anatomical_side": side}))
    (analysis / "camera_repetition_features.json").write_text(json.dumps([{
        "rep_id": 1, "normalized_hip_displacement": [[500, .3]], "alignment_angle_deviation_deg": [[500, 42]]}]))
    landmarks = {f"left_{name}": {"x": x, "y": y, "visibility": visibility, "presence": 1}
                 for name, x, y in (("shoulder", .1, .5), ("hip", .5, .8), ("ankle", .9, .5))}
    (analysis / "video_observations.jsonl").write_text(json.dumps({"timestamp_ms": 500, "pose": {"detected": True, "landmarks": landmarks},
                                                              "image_width_px": 400, "image_height_px": 320}) + "\n")
    return folder


def test_review_moment_matches_frozen_geometry(tmp_path):
    moment = review_moments(fixture(tmp_path))["moments"][0]
    assert moment["timestamp_ms"] == 500
    assert moment["landmark_names"] == ("left_shoulder", "left_hip", "left_ankle")
    assert moment["normalized_hip_displacement"] == .3
    assert moment["target"]["y"] == .5


def test_review_moment_abstains_on_unavailable_or_bad_landmarks(tmp_path):
    assert review_moments(fixture(tmp_path / "a", visibility=.2)) == {"moments": []}
    assert review_moments(fixture(tmp_path / "b", result="unavailable")) == {"moments": []}
    assert review_moments(fixture(tmp_path / "c", side="right")) == {"moments": []}
