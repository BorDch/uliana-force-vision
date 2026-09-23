import csv,json,sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).parents[1]/"scripts"))
from evaluate_camera_sessions import evaluate


def write_manifest(path,rows):
    with path.open("w",newline="") as handle:
        writer=csv.DictWriter(handle,fieldnames=["participant_id","session_id","true_viewpoint","expected_repetitions","split"]);writer.writeheader();writer.writerows(rows)


def test_participant_leakage_is_rejected(tmp_path):
    manifest=tmp_path/"manifest.csv";write_manifest(manifest,[{"participant_id":"p1","session_id":"s1","true_viewpoint":"side","expected_repetitions":"1","split":"development"},{"participant_id":"p1","session_id":"s2","true_viewpoint":"side","expected_repetitions":"1","split":"test"}])
    with pytest.raises(ValueError,match="leakage"):evaluate(manifest,tmp_path,tmp_path)
