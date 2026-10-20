"""Tests for reusable feature and model JSON contract conversion."""

import subprocess
import sys
from pathlib import Path


def test_serializers_are_usable_without_typer_or_entry_point() -> None:
    src_dir = Path(__file__).resolve().parents[3] / "src"
    script = f"""import sys
sys.path.insert(0, {str(src_dir)!r})
sys.modules['typer'] = None
from make_features.serialization.inputs import parse_explanatory_inputs
from make_features.serialization.outputs import feature_audit_payload
from models.serialization.inputs import parse_feature_inputs
from models.serialization.outputs import metrics_payload
from data.saver.write_json import write_json
assert parse_explanatory_inputs({{'records': []}}) == ()
assert 'main' not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
