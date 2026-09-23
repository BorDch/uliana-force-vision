from pathlib import Path
import pytest

from uliana.config import load_config


@pytest.fixture
def config():
    return load_config(Path(__file__).parents[1] / "configs" / "toy_experiment.json")

