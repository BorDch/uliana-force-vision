from __future__ import annotations

import hashlib,json,subprocess
from datetime import datetime,timezone
from pathlib import Path


class StaleCacheError(RuntimeError):pass


def sha256_file(path:Path)->str:
    digest=hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda:handle.read(1024*1024),b""):digest.update(block)
    return digest.hexdigest()


def _hashes(paths:dict[str,Path|None])->dict[str,str]:
    return {name:sha256_file(path) for name,path in paths.items() if path is not None and path.exists()}


def build_provenance(*,inputs:dict[str,Path|None],configs:dict[str,Path|None],model:Path|None,
                     calibration_id:str|None,synchronization_method:str|None,data_declaration:str,
                     source_video:dict|None=None,pressure_source:str|None=None)->dict:
    try:commit=subprocess.run(["git","rev-parse","HEAD"],capture_output=True,text=True,check=True).stdout.strip()
    except (OSError,subprocess.CalledProcessError):commit=None
    return {"schema_version":"1.0","processed_at":datetime.now(timezone.utc).isoformat(),
        "input_hashes":_hashes(inputs),"configuration_hashes":_hashes(configs),
        "model_hash":sha256_file(model) if model and model.exists() else None,"model_path":str(model) if model else None,
        "calibration_id":calibration_id,"contract_schema_versions":{"video_observation":"1.0","pressure_observation":"1.0","session_result":"1.0"},
        "source_video":source_video,"pressure_source":pressure_source,"synchronization_method":synchronization_method,
        "software_version":"0.1.0","git_commit":commit,"data_declaration":data_declaration}


def verify_cache(manifest_path:Path,*,inputs:dict[str,Path|None],configs:dict[str,Path|None],model:Path|None)->dict:
    try:manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError) as exc:raise StaleCacheError(f"cache manifest unavailable: {exc}") from exc
    expected_inputs=_hashes(inputs);expected_configs=_hashes(configs);expected_model=sha256_file(model) if model and model.exists() else None
    if manifest.get("input_hashes")!=expected_inputs:raise StaleCacheError("cached artifact input/source hash mismatch")
    if manifest.get("configuration_hashes")!=expected_configs:raise StaleCacheError("cached artifact configuration hash mismatch")
    if manifest.get("model_hash")!=expected_model:raise StaleCacheError("cached artifact model hash mismatch")
    return manifest
