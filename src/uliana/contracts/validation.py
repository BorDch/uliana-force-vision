from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

SCHEMA_DIRECTORY = Path(__file__).resolve().parents[3] / "schemas"
SCHEMAS = {
    "video_observation": "video-observation.schema.json",
    "pressure_observation": "pressure-observation.schema.json",
    "session_result": "session-result.schema.json",
    "metadata": "metadata.schema.json",
}


class ContractValidationError(ValueError):
    pass


def load_schema(kind: str) -> dict[str, Any]:
    try:
        name = SCHEMAS[kind]
    except KeyError as exc:
        raise ValueError(f"unknown contract kind: {kind}") from exc
    return json.loads((SCHEMA_DIRECTORY / name).read_text(encoding="utf-8"))


def validate_contract(kind: str, value: Any) -> None:
    payload = value.to_dict() if hasattr(value, "to_dict") else value
    errors = sorted(Draft202012Validator(load_schema(kind)).iter_errors(payload), key=lambda error: list(error.path))
    if errors:
        details = "; ".join(f"{'/'.join(map(str, error.path)) or '<root>'}: {error.message}" for error in errors)
        raise ContractValidationError(details)
