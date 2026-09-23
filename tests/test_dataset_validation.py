import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from validate_dataset import validate_dataset

FIXTURE = Path(__file__).parent / "fixtures" / "dataset"


def errors(findings):
    return [item for item in findings if item.level == "ERROR"]


def test_committed_multimodal_fixture_is_valid():
    assert not errors(validate_dataset(FIXTURE / "raw"))


def test_valid_camera_only_session_reports_optional_pressure(tmp_path):
    destination = tmp_path / "data"
    shutil.copytree(FIXTURE, destination)
    (destination / "raw/anon-p001/session-fixture/pressure.csv").unlink()
    findings = validate_dataset(destination / "raw")
    assert not errors(findings)
    assert any(item.level == "INFO" and "pressure" in item.message for item in findings)


def test_non_monotonic_and_duplicate_channel_timestamps(tmp_path):
    destination = tmp_path / "data"
    shutil.copytree(FIXTURE, destination)
    pressure = destination / "raw/anon-p001/session-fixture/pressure.csv"
    pressure.write_text(pressure.read_text() + "20,device_clock,mat-fixture,cell_00,0,0,104,10.4,calibrated,\n10,device_clock,mat-fixture,cell_00,0,0,105,10.5,calibrated,\n")
    messages = [item.message for item in errors(validate_dataset(destination / "raw"))]
    assert any("duplicate timestamp" in message for message in messages)
    assert any("non-monotonic" in message for message in messages)


def test_participant_and_session_directory_mismatch_is_rejected(tmp_path):
    destination = tmp_path / "data"
    shutil.copytree(FIXTURE, destination)
    metadata_path = destination / "raw/anon-p001/session-fixture/metadata.json"
    metadata = json.loads(metadata_path.read_text()); metadata["session_id"] = "different-session"
    metadata_path.write_text(json.dumps(metadata))
    assert any("do not match metadata" in item.message for item in errors(validate_dataset(destination / "raw")))


def test_invalid_metadata_enum_is_rejected(tmp_path):
    destination = tmp_path / "data"
    shutil.copytree(FIXTURE, destination)
    metadata_path = destination / "raw/anon-p001/session-fixture/metadata.json"
    metadata = json.loads(metadata_path.read_text()); metadata["camera_viewpoint"] = "360_degree"
    metadata_path.write_text(json.dumps(metadata))
    assert errors(validate_dataset(destination / "raw"))
