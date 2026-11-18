"""Write and read the ADR-045 race-day betting estimator artifact."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from fractions import Fraction
from pathlib import Path

import pytest

from models.artifacts.betting_estimator import (
    MANIFEST_FILE,
    manifest_from_record,
    read_betting_estimator,
    write_betting_estimator,
)
from tests.betting_estimator_fixtures import estimator_record

ODDS = (1.0, 1.2, 1.5, 1.99, 2.0, 2.01, 3.0, 4.0, 6.0, 30.0, 500.0)
WIDTHS = (Fraction(1), Fraction(149, 100), Fraction(3, 2), Fraction(2), Fraction(3), Fraction(9))
Manifest = dict[str, object]


def _write(directory: Path, manifest: Manifest | None = None) -> str:
    directory.mkdir()
    if manifest is None:
        return write_betting_estimator(directory, estimator_record())
    payload = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode("ascii")
    (directory / MANIFEST_FILE).write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


@pytest.mark.parametrize(
    ("method", "graded", "min_hits"),
    [("pl_mid", False, 1), ("blend_width", True, 1), ("blend_width", True, 2)],
)
def test_a_written_artifact_reads_back_with_identical_estimates(
    tmp_path: Path, method: str, graded: bool, min_hits: int
) -> None:
    record = estimator_record(winner=method, graded=graded, min_hits=min_hits)  # type: ignore[arg-type]
    graded_counts = [
        band.hit_count
        for correction in (record.mid, *record.width.corrections)
        for band in correction.bands
    ]
    # The graded records mix empty and fitted graded bands; the other has none fitted.
    assert (0 in graded_counts, any(graded_counts)) == (True, graded)
    # With min_hits=2 one place_mid band keeps the all-races quantiles and the other its
    # own, and every fitted width band keeps the all-races quantiles.
    assert record.settings.min_hits == min_hits
    mid_counts = [band.hit_count for band in record.mid.bands]
    assert (1 in mid_counts, 2 in mid_counts) == (graded, graded)
    assert any(0 < count < min_hits for count in graded_counts) == (min_hits > 1)
    directory = tmp_path / "estimator"
    directory.mkdir()

    digest = write_betting_estimator(directory, record)
    read = read_betting_estimator(directory, expected_manifest_sha256=digest)

    assert digest == hashlib.sha256((directory / MANIFEST_FILE).read_bytes()).hexdigest()
    assert [path.name for path in directory.iterdir()] == [MANIFEST_FILE]
    assert read.record.method == method
    assert read.record.target_year == 2025
    assert read.record.policy == record.policy
    assert (read.record.blend.alpha, read.record.blend.beta) == (
        record.blend.alpha,
        record.blend.beta,
    )
    assert read.record.width.width_edges == record.width.width_edges
    for odds in ODDS:
        assert read.record.mid.estimate(odds) == record.mid.estimate(odds)
        for width in WIDTHS:
            assert read.record.width.estimate(odds, width) == record.width.estimate(odds, width)
    assert manifest_from_record(read.record) == manifest_from_record(record)


def test_a_staging_that_is_not_empty_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "other").write_text("x", encoding="utf-8")

    with pytest.raises(ValueError, match="empty directory"):
        write_betting_estimator(tmp_path, estimator_record())


def test_the_identity_and_the_file_set_are_checked(tmp_path: Path) -> None:
    directory = tmp_path / "estimator"
    digest = _write(directory)

    with pytest.raises(ValueError, match="differs from the expected identity"):
        read_betting_estimator(directory, expected_manifest_sha256="0" * 64)
    with pytest.raises(ValueError, match="64 lowercase hex"):
        read_betting_estimator(directory, expected_manifest_sha256="ABC")
    (directory / "extra.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match=r"exactly manifest.json"):
        read_betting_estimator(directory, expected_manifest_sha256=digest)


def _edit(change: Callable[[Manifest], None]) -> Manifest:
    record = estimator_record(graded=True)
    manifest: Manifest = json.loads(json.dumps(manifest_from_record(record)))
    change(manifest)
    return manifest


def _set(path: str, value: object) -> Callable[[Manifest], None]:
    def change(manifest: Manifest) -> None:
        *parents, last = path.split(".")
        node: object = manifest
        for name in parents:
            node = node[int(name)] if isinstance(node, list) else node[name]  # type: ignore[index]
        if isinstance(node, list):
            node[int(last)] = value
        else:
            node[last] = value  # type: ignore[index]

    return change


def _drop(path: str) -> Callable[[Manifest], None]:
    def change(manifest: Manifest) -> None:
        *parents, last = path.split(".")
        node: object = manifest
        for name in parents:
            node = node[name]  # type: ignore[index]
        del node[last]  # type: ignore[attr-defined]

    return change


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (_set("format_version", 2), "format"),
        (_drop("provenance"), "keys differ"),
        (_set("extra", 1), "keys differ"),
        (_set("target_year", True), "target_year"),
        (_set("method", "other"), "method must be one of"),
        (_set("method", "pl_mid"), "differs from its recorded selection"),
        (_set("selection.comparison_years", [2023]), "flat must cover"),
        (_set("selection.flat.pl_mid.2023.stake_yen", 1.5), "stake_yen"),
        (_set("blend.alpha", None), "alpha"),
        (_set("blend.failure", "unknown"), "failure"),
        (_set("blend.tolerance", 1e-6), "tolerance"),
        (_set("blend.fit_years", [2023, 2025]), "precede target_year"),
        (_set("final_odds.train_end_year", 2023), "train_end_year"),
        (_set("final_odds.train_start_year", 2025), "train_start_year"),
        (_set("final_odds.place_width_bands", [1.0, 1.5]), "width_edges_tenths"),
        (_set("place_width.groups", [[0, 1], [3], [2], [4]]), "partition"),
        (_set("place_width.hit_counts", [1]), "one hit count"),
        (_set("place_mid.graded.band_edges", [1.0, 3.0]), "differ from final_odds"),
        (_set("place_mid.graded.bands.0.lower", 1.5), "partition"),
        (_set("place_mid.all.bands.0.ratio_quantiles", [1.0]), "quantile levels"),
        (_set("place_mid.all.bands.0.ratio_quantiles", [1.2, 1.0, 1.4]), "quantile levels"),
        (_set("place_mid.all.bands.0.ratio_quantiles", [0.0, 1.0, 1.4]), "quantile levels"),
        (_set("place_mid.all.bands.0.mean_ratio", -1.0), "mean_ratio must be positive"),
        (_set("place_mid.all.bands.0.mean_ratio", None), "an all band"),
        (_set("place_mid.all.bands.0.shrinkage_k", 2), "an all band"),
        (_set("place_mid.graded.bands.0.shrinkage_k", None), "shrinkage_k"),
        (_set("place_mid.graded.bands.0.hit_count", 0), "exactly when hits do"),
        (_set("place_mid.graded.bands.0.shrinkage_k", 7), "shrinkage_k"),
        (_set("place_mid.graded.bands.0.source_lowers", [1.0, 2.0]), "never merged"),
        (_set("place_mid.all.bands.0.hit_count", 0), "an all band has hits"),
        (_set("final_odds.place_mid_hits", 999), "place_mid_hits"),
        (_set("final_odds.width_observations", 999), "place_width hit counts"),
        (_set("policy.unit_yen", 150), "multiple of 100"),
        (_set("policy.race_budget_yen", False), "race_budget_yen"),
        (_set("sources.snapshot.snapshot_id", "../x"), "snapshot_id"),
    ],
)
def test_a_manifest_that_breaks_a_rule_is_rejected(
    tmp_path: Path, change: Callable[[Manifest], None], message: str
) -> None:
    directory = tmp_path / "estimator"
    digest = _write(directory, _edit(change))

    with pytest.raises(ValueError, match=message):
        read_betting_estimator(directory, expected_manifest_sha256=digest)


def test_the_writer_rejects_a_record_the_reader_would_reject(tmp_path: Path) -> None:
    from dataclasses import replace

    record = replace(estimator_record(), method="pl_mid")
    tmp_path.joinpath("estimator").mkdir()

    with pytest.raises(ValueError, match="recorded selection"):
        write_betting_estimator(tmp_path / "estimator", record)
    assert list((tmp_path / "estimator").iterdir()) == []
