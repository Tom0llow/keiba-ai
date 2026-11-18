"""Write and read the race-day betting estimator artifact (ADR-045).

An artifact is one directory with exactly ``manifest.json``. It holds one target year's
ADR-044 method, chosen by Decision 4 from a backtest's flat results, the ADR-043 policy,
and the fits that every method needs: the graded ``place_mid`` correction, the
width-banded place correction and the PL-market blend, each from data before the
target year only. The manifest is identified by the SHA-256 of its bytes; every reader
passes that identity explicitly. Like ``pl_model.py``, this module owns its small byte
I/O and imports neither ``data`` nor the CLI.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from itertools import pairwise
from math import isfinite
from pathlib import Path
from typing import cast, get_args

from models.betting.methods import METHODS, Method, select_method
from models.betting.policy import BettingPolicy
from models.market.final_odds_correction import (
    CorrectionBand,
    FinalOddsCorrection,
    validate_odds_bands,
    validate_quantiles,
)
from models.market.place_width_correction import PlaceWidthCorrection, validate_width_bands
from models.probability.market_blend import MAX_TOLERANCE, BlendFailure, BlendFit

FORMAT = "ev_betting_estimator"
FORMAT_VERSION = 1
MANIFEST_FILE = "manifest.json"
BLEND_EXCLUSIONS = ("market_incomplete", "zero_probability", "winner_count")
_HEX64 = re.compile(r"[0-9a-f]{64}")
# The fixed snapshot naming rule (data.loader.fixed_snapshot).
_SNAPSHOT_ID = re.compile(r"[A-Za-z0-9_-]+")
_POLICY_KEYS = (
    "min_expected_return",
    "kelly_fraction",
    "bankroll_yen",
    "annual_budget_yen",
    "race_budget_yen",
    "unit_yen",
)
_TOP_KEYS = frozenset(
    {
        "format",
        "format_version",
        "target_year",
        "method",
        "selection",
        "policy",
        "final_odds",
        "place_mid",
        "place_width",
        "blend",
        "sources",
        "provenance",
    }
)
_FINAL_ODDS_KEYS = frozenset(
    {
        "train_start_year",
        "train_end_year",
        "max_publication_age_seconds",
        "place_mid_bands",
        "quantiles",
        "min_hits",
        "graded_shrinkage_k",
        "place_width_bands",
        "place_mid_hits",
        "width_observations",
    }
)
_CORRECTION_KEYS = frozenset({"band_edges", "quantile_levels", "bands"})
_BAND_KEYS = frozenset(
    {
        "lower",
        "upper",
        "source_lowers",
        "hit_count",
        "mean_ratio",
        "mean_log_freeze_odds",
        "ratio_quantiles",
        "shrinkage_target",
        "shrinkage_k",
    }
)
_GRADED_KEYS = frozenset({"graded", "all"})
_WIDTH_KEYS = frozenset({"width_edges_tenths", "groups", "hit_counts", "corrections"})
_BLEND_KEYS = frozenset(
    {
        "alpha",
        "beta",
        "races",
        "iterations",
        "failure",
        "excluded",
        "fit_years",
        "min_races",
        "tolerance",
        "max_iterations",
    }
)
_SELECTION_KEYS = frozenset({"comparison_years", "flat"})
_FLAT_KEYS = frozenset({"stake_yen", "receipt_yen"})
_SOURCE_KEYS = frozenset({"backtest_report_sha256", "pl_evaluation", "snapshot"})
_PL_SOURCE_KEYS = frozenset({"report_sha256", "predictions_sha256", "variant"})
_SNAPSHOT_KEYS = frozenset({"snapshot_id", "tables"})


@dataclass(frozen=True)
class EstimatorSettings:
    """Hold the backtest's fixed fitting settings that the artifact repeats."""

    train_start_year: int
    max_publication_age_seconds: int
    place_mid_bands: tuple[float, ...]
    quantiles: tuple[float, ...]
    min_hits: int
    graded_shrinkage_k: int
    place_width_bands: tuple[float, ...]
    blend_min_races: int
    blend_tolerance: float
    blend_max_iterations: int


@dataclass(frozen=True)
class BettingEstimatorRecord:
    """Hold everything the artifact records for one target year.

    ``flat`` maps each method to its flat ``(receipt_yen, stake_yen)`` of each
    comparison year. ``sources`` holds the SHA-256 identities of the backtest report, the
    PL evaluation and the snapshot tables; ``provenance`` is the build's provenance.
    """

    target_year: int
    method: Method
    comparison_years: tuple[int, ...]
    flat: Mapping[Method, Mapping[int, tuple[int, int]]]
    policy: BettingPolicy
    settings: EstimatorSettings
    place_mid_hits: int
    width_observations: int
    mid: FinalOddsCorrection
    width: PlaceWidthCorrection
    blend: BlendFit
    blend_excluded: Mapping[str, int]
    blend_fit_years: tuple[int, ...]
    sources: Mapping[str, object]
    provenance: Mapping[str, object]


@dataclass(frozen=True)
class BettingEstimator:
    """Hold a validated artifact: its identity, manifest and decoded fits."""

    manifest_sha256: str
    manifest: Mapping[str, object]
    record: BettingEstimatorRecord


def write_betting_estimator(directory: Path, record: BettingEstimatorRecord) -> str:
    """Write the artifact into an existing empty directory and return its manifest SHA-256.

    The manifest built from ``record`` is validated with the reader's rules and
    serialized as strict JSON before the file is written, so a record the reader would
    reject leaves the directory empty. The caller owns the directory, removes it on
    failure and publishes it on success.

    Raises:
        ValueError: If the directory is missing or not empty, or the manifest is invalid.
    """
    if not directory.is_dir() or any(directory.iterdir()):
        raise ValueError("betting estimator staging must be an existing empty directory")
    payload = _manifest_payload(manifest_from_record(record))
    with (directory / MANIFEST_FILE).open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    return hashlib.sha256(payload).hexdigest()


def read_betting_estimator(path: Path, *, expected_manifest_sha256: str) -> BettingEstimator:
    """Read and validate a betting estimator artifact pinned by its manifest SHA-256.

    Raises:
        ValueError: If the identity, the file set or any manifest rule differs.
    """
    if not isinstance(expected_manifest_sha256, str) or not _HEX64.fullmatch(
        expected_manifest_sha256
    ):
        raise ValueError("expected_manifest_sha256 must be 64 lowercase hex digits")
    root = path.resolve()
    if not root.is_dir():
        raise ValueError("betting estimator path must be a directory")
    if [item.name for item in root.iterdir()] != [MANIFEST_FILE]:
        raise ValueError("betting estimator directory must hold exactly manifest.json")
    payload = (root / MANIFEST_FILE).read_bytes()
    if hashlib.sha256(payload).hexdigest() != expected_manifest_sha256:
        raise ValueError("betting estimator manifest SHA-256 differs from the expected identity")
    try:
        manifest = json.loads(payload, parse_constant=_reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("betting estimator manifest is not valid JSON") from exc
    if not isinstance(manifest, dict):
        raise ValueError("betting estimator manifest must be a JSON object")
    record = record_from_manifest(manifest)
    return BettingEstimator(expected_manifest_sha256, manifest, record)


def manifest_from_record(record: BettingEstimatorRecord) -> dict[str, object]:
    """Return the manifest of ``record`` (not yet validated)."""
    settings = record.settings
    policy = record.policy
    fit = record.blend
    return {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "target_year": record.target_year,
        "method": record.method,
        "selection": {
            "comparison_years": list(record.comparison_years),
            "flat": {
                method: {
                    str(year): {"receipt_yen": receipt, "stake_yen": stake}
                    for year, (receipt, stake) in sorted(record.flat.get(method, {}).items())
                }
                for method in METHODS
            },
        },
        "policy": {name: getattr(policy, name) for name in _POLICY_KEYS},
        "final_odds": {
            "train_start_year": settings.train_start_year,
            "train_end_year": record.target_year - 1,
            "max_publication_age_seconds": settings.max_publication_age_seconds,
            "place_mid_bands": list(settings.place_mid_bands),
            "quantiles": list(settings.quantiles),
            "min_hits": settings.min_hits,
            "graded_shrinkage_k": settings.graded_shrinkage_k,
            "place_width_bands": list(settings.place_width_bands),
            "place_mid_hits": record.place_mid_hits,
            "width_observations": record.width_observations,
        },
        "place_mid": _graded_payload(record.mid),
        "place_width": {
            "width_edges_tenths": [_tenths(edge) for edge in record.width.width_edges],
            "groups": [list(group) for group in record.width.groups],
            "hit_counts": list(record.width.hit_counts),
            "corrections": [_graded_payload(item) for item in record.width.corrections],
        },
        "blend": {
            "alpha": fit.alpha,
            "beta": fit.beta,
            "races": fit.races,
            "iterations": fit.iterations,
            "failure": fit.failure,
            "excluded": {name: record.blend_excluded[name] for name in BLEND_EXCLUSIONS},
            "fit_years": list(record.blend_fit_years),
            "min_races": settings.blend_min_races,
            "tolerance": settings.blend_tolerance,
            "max_iterations": settings.blend_max_iterations,
        },
        "sources": dict(record.sources),
        "provenance": dict(record.provenance),
    }


def record_from_manifest(manifest: Mapping[str, object]) -> BettingEstimatorRecord:
    """Validate a manifest and decode it into a record.

    Raises:
        ValueError: If a key, type, constant or consistency rule differs from the format.
    """
    _keys(manifest, _TOP_KEYS, "manifest")
    if manifest["format"] != FORMAT or manifest["format_version"] != FORMAT_VERSION:
        raise ValueError("unsupported betting estimator format or format_version")
    target_year = _integer(manifest["target_year"], "target_year", minimum=1)
    method = manifest["method"]
    if method not in METHODS:
        raise ValueError(f"betting estimator method must be one of {list(METHODS)}")
    final_odds = _keys(manifest["final_odds"], _FINAL_ODDS_KEYS, "final_odds")
    blend_payload = _keys(manifest["blend"], _BLEND_KEYS, "blend")
    settings = EstimatorSettings(
        train_start_year=_integer(final_odds["train_start_year"], "train_start_year", minimum=1),
        max_publication_age_seconds=_integer(
            final_odds["max_publication_age_seconds"], "max_publication_age_seconds", minimum=1
        ),
        place_mid_bands=validate_odds_bands(_numbers(final_odds["place_mid_bands"], "bands")),
        quantiles=validate_quantiles(_numbers(final_odds["quantiles"], "quantiles")),
        min_hits=_integer(final_odds["min_hits"], "min_hits", minimum=1),
        graded_shrinkage_k=_integer(
            final_odds["graded_shrinkage_k"], "graded_shrinkage_k", minimum=0
        ),
        place_width_bands=_numbers(final_odds["place_width_bands"], "place_width_bands"),
        blend_min_races=_integer(blend_payload["min_races"], "blend.min_races", minimum=1),
        blend_tolerance=_number(blend_payload["tolerance"], "blend.tolerance"),
        blend_max_iterations=_integer(
            blend_payload["max_iterations"], "blend.max_iterations", minimum=1
        ),
    )
    if not 0.0 < settings.blend_tolerance <= MAX_TOLERANCE:
        raise ValueError(f"blend.tolerance must be positive and at most {MAX_TOLERANCE:g}")
    width_edges = validate_width_bands(settings.place_width_bands)
    if _integer(final_odds["train_end_year"], "train_end_year", minimum=1) != target_year - 1:
        raise ValueError("final_odds.train_end_year must be the year before target_year")
    if settings.train_start_year >= target_year:
        raise ValueError("final_odds.train_start_year must precede target_year")
    policy_payload = _keys(manifest["policy"], frozenset(_POLICY_KEYS), "policy")
    for name in _POLICY_KEYS[2:]:
        _integer(policy_payload[name], f"policy.{name}", minimum=1)
    policy = BettingPolicy(
        min_expected_return=_number(policy_payload["min_expected_return"], "policy"),
        kelly_fraction=_number(policy_payload["kelly_fraction"], "policy"),
        bankroll_yen=cast(int, policy_payload["bankroll_yen"]),
        annual_budget_yen=cast(int, policy_payload["annual_budget_yen"]),
        race_budget_yen=cast(int, policy_payload["race_budget_yen"]),
        unit_yen=cast(int, policy_payload["unit_yen"]),
    )
    mid = _graded_correction(manifest["place_mid"], settings, "place_mid")
    width = _width_correction(manifest["place_width"], settings, width_edges)
    place_mid_hits = _integer(final_odds["place_mid_hits"], "place_mid_hits", minimum=1)
    width_observations = _integer(final_odds["width_observations"], "width_observations", minimum=1)
    if _all_hits(mid) != place_mid_hits:
        raise ValueError("place_mid hits differ from final_odds.place_mid_hits")
    if sum(width.hit_counts) != width_observations or any(
        _all_hits(correction) != count
        for correction, count in zip(width.corrections, width.hit_counts, strict=True)
    ):
        raise ValueError("place_width hit counts differ from their fits")
    blend, excluded, fit_years = _blend(blend_payload, target_year)
    comparison, flat = _selection(manifest["selection"], target_year)
    available = frozenset(
        name for name in METHODS if not name.startswith("blend") or blend.available
    )
    chosen, derived = select_method(flat, comparison, target_year, available=available)
    if derived != comparison or chosen != method:
        raise ValueError("betting estimator method differs from its recorded selection")
    sources = _sources(manifest["sources"])
    if not isinstance(manifest["provenance"], dict):
        raise ValueError("betting estimator provenance must be an object")
    return BettingEstimatorRecord(
        target_year=target_year,
        method=cast(Method, method),
        comparison_years=comparison,
        flat=flat,
        policy=policy,
        settings=settings,
        place_mid_hits=place_mid_hits,
        width_observations=width_observations,
        mid=mid,
        width=width,
        blend=blend,
        blend_excluded=excluded,
        blend_fit_years=fit_years,
        sources=sources,
        provenance=cast(dict[str, object], manifest["provenance"]),
    )


def _manifest_payload(manifest: Mapping[str, object]) -> bytes:
    """Validate the manifest and return its ASCII JSON bytes (sorted keys, no NaN)."""
    try:
        text = json.dumps(manifest, sort_keys=True, ensure_ascii=True, allow_nan=False, indent=2)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"betting estimator manifest is not strict JSON: {exc}") from exc
    # Validate the decoded JSON, as a reader sees it.
    record_from_manifest(json.loads(text))
    return (text + "\n").encode("ascii")


def _correction_payload(correction: FinalOddsCorrection) -> dict[str, object]:
    return {
        "band_edges": list(correction.band_edges),
        "quantile_levels": list(correction.quantile_levels),
        "bands": [
            {
                "lower": band.lower,
                "upper": band.upper,
                "source_lowers": list(band.source_lowers),
                "hit_count": band.hit_count,
                "mean_ratio": band.mean_ratio,
                "mean_log_freeze_odds": band.mean_log_freeze_odds,
                "ratio_quantiles": None
                if band.ratio_quantiles is None
                else list(band.ratio_quantiles),
                "shrinkage_target": band.shrinkage_target,
                "shrinkage_k": band.shrinkage_k,
            }
            for band in correction.bands
        ],
    }


def _graded_payload(correction: FinalOddsCorrection) -> dict[str, object]:
    fallback = correction.quantile_fallback
    if fallback is None or fallback.quantile_fallback is not None:
        raise ValueError("a graded correction must fall back to exactly one all correction")
    return {"graded": _correction_payload(correction), "all": _correction_payload(fallback)}


def _graded_correction(
    value: object, settings: EstimatorSettings, where: str
) -> FinalOddsCorrection:
    payload = _keys(value, _GRADED_KEYS, where)
    graded = _correction(payload["graded"], settings, f"{where}.graded", graded=True)
    fallback = _correction(payload["all"], settings, f"{where}.all", graded=False)
    return graded.with_quantile_fallback(fallback)


def _correction(
    value: object, settings: EstimatorSettings, where: str, *, graded: bool
) -> FinalOddsCorrection:
    """Decode one correction; an ``all`` fit has every band, a graded fit may be empty."""
    payload = _keys(value, _CORRECTION_KEYS, where)
    edges = validate_odds_bands(_numbers(payload["band_edges"], f"{where}.band_edges"))
    levels = validate_quantiles(_numbers(payload["quantile_levels"], f"{where}.quantile_levels"))
    if edges != settings.place_mid_bands or levels != settings.quantiles:
        raise ValueError(f"{where} bands or quantiles differ from final_odds")
    raw = payload["bands"]
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"{where}.bands must be a non-empty list")
    bands = tuple(
        _band(
            item,
            levels,
            f"{where}.bands",
            graded=graded,
            expected_shrinkage_k=settings.graded_shrinkage_k,
        )
        for item in raw
    )
    sources = [lower for band in bands for lower in band.source_lowers]
    if tuple(sources) != edges or bands[0].lower != edges[0] or bands[-1].upper is not None:
        raise ValueError(f"{where}.bands must partition the configured bands in order")
    for left, right in pairwise(bands):
        if left.upper != right.lower or left.source_lowers[0] != left.lower:
            raise ValueError(f"{where}.bands must be contiguous")
    if bands[-1].source_lowers[0] != bands[-1].lower:
        raise ValueError(f"{where}.bands must be contiguous")
    return FinalOddsCorrection(edges, levels, bands)


def _band(
    value: object,
    levels: tuple[float, ...],
    where: str,
    *,
    graded: bool,
    expected_shrinkage_k: int,
) -> CorrectionBand:
    payload = _keys(value, _BAND_KEYS, where)
    upper = payload["upper"]
    ratios = payload["ratio_quantiles"]
    shrinkage_target = payload["shrinkage_target"]
    shrinkage_k = payload["shrinkage_k"]
    band = CorrectionBand(
        lower=_number(payload["lower"], f"{where}.lower"),
        upper=None if upper is None else _number(upper, f"{where}.upper"),
        source_lowers=_numbers(payload["source_lowers"], f"{where}.source_lowers"),
        hit_count=_integer(payload["hit_count"], f"{where}.hit_count", minimum=0),
        mean_ratio=_optional_number(payload["mean_ratio"], f"{where}.mean_ratio"),
        mean_log_freeze_odds=_optional_number(
            payload["mean_log_freeze_odds"], f"{where}.mean_log_freeze_odds"
        ),
        ratio_quantiles=None if ratios is None else _numbers(ratios, f"{where}.ratio_quantiles"),
        shrinkage_target=_optional_number(shrinkage_target, f"{where}.shrinkage_target"),
        shrinkage_k=None
        if shrinkage_k is None
        else _integer(shrinkage_k, f"{where}.shrinkage_k", minimum=0),
    )
    fitted = (band.mean_ratio, band.mean_log_freeze_odds, band.ratio_quantiles)
    if graded:
        # A graded band without hits keeps no values; one with hits keeps them all.
        if (band.hit_count == 0) != all(item is None for item in fitted) or any(
            (item is None) != (band.hit_count == 0) for item in (*fitted, band.shrinkage_target)
        ):
            raise ValueError(f"{where}: fitted values must exist exactly when hits do")
        if band.shrinkage_k != expected_shrinkage_k:
            raise ValueError(f"{where}: a graded band records final_odds' shrinkage_k")
        if len(band.source_lowers) != 1:
            raise ValueError(f"{where}: a graded band is never merged")
    elif band.hit_count < 1:
        raise ValueError(f"{where}: an all band has hits")
    elif any(item is None for item in fitted) or (
        band.shrinkage_target is not None or band.shrinkage_k is not None
    ):
        raise ValueError(f"{where}: an all band has fitted values and no shrinkage")
    if band.mean_ratio is not None and band.mean_ratio <= 0.0:
        raise ValueError(f"{where}.mean_ratio must be positive")
    if band.ratio_quantiles is not None and (
        len(band.ratio_quantiles) != len(levels)
        or band.ratio_quantiles[0] <= 0.0
        or any(right < left for left, right in pairwise(band.ratio_quantiles))
    ):
        raise ValueError(f"{where}.ratio_quantiles must match the quantile levels")
    if band.upper is not None and band.upper <= band.lower:
        raise ValueError(f"{where}: upper must exceed lower")
    return band


def _width_correction(
    value: object, settings: EstimatorSettings, edges: tuple[Fraction, ...]
) -> PlaceWidthCorrection:
    payload = _keys(value, _WIDTH_KEYS, "place_width")
    tenths = payload["width_edges_tenths"]
    if (
        not isinstance(tenths, list)
        or any(isinstance(item, bool) or not isinstance(item, int) for item in tenths)
        or tuple(Fraction(cast(int, item), 10) for item in tenths) != edges
    ):
        raise ValueError("place_width.width_edges_tenths differ from final_odds")
    groups_payload = payload["groups"]
    if not isinstance(groups_payload, list) or not groups_payload:
        raise ValueError("place_width.groups must be a non-empty list")
    groups: list[tuple[int, ...]] = []
    for group in groups_payload:
        if not isinstance(group, list) or not group:
            raise ValueError("place_width.groups must hold non-empty lists")
        groups.append(tuple(_integer(item, "place_width.groups", minimum=0) for item in group))
    if [index for group in groups for index in group] != list(range(len(edges))):
        raise ValueError("place_width.groups must partition the width bands in order")
    counts = payload["hit_counts"]
    corrections = payload["corrections"]
    if (
        not isinstance(counts, list)
        or not isinstance(corrections, list)
        or len(counts) != len(groups)
        or len(corrections) != len(groups)
    ):
        raise ValueError("place_width needs one hit count and correction per group")
    return PlaceWidthCorrection(
        edges,
        tuple(groups),
        tuple(
            _graded_correction(item, settings, f"place_width.corrections[{index}]")
            for index, item in enumerate(corrections)
        ),
        tuple(_integer(item, "place_width.hit_counts", minimum=1) for item in counts),
    )


def _blend(
    payload: Mapping[str, object], target_year: int
) -> tuple[BlendFit, dict[str, int], tuple[int, ...]]:
    failure = payload["failure"]
    if failure is not None and failure not in get_args(BlendFailure):
        raise ValueError("blend.failure is not a known failure")
    alpha, beta = payload["alpha"], payload["beta"]
    fitted: tuple[float, float] | tuple[None, None]
    if failure is None:
        fitted = (_number(alpha, "blend.alpha"), _number(beta, "blend.beta"))
    elif alpha is not None or beta is not None:
        raise ValueError("a failed blend must not record coefficients")
    else:
        fitted = (None, None)
    excluded_payload = _keys(payload["excluded"], frozenset(BLEND_EXCLUSIONS), "blend.excluded")
    excluded = {
        name: _integer(excluded_payload[name], f"blend.excluded.{name}", minimum=0)
        for name in BLEND_EXCLUSIONS
    }
    fit_years = _years(payload["fit_years"], "blend.fit_years", target_year)
    fit = BlendFit(
        alpha=fitted[0],
        beta=fitted[1],
        races=_integer(payload["races"], "blend.races", minimum=0),
        iterations=_integer(payload["iterations"], "blend.iterations", minimum=0),
        failure=cast(BlendFailure | None, failure),
    )
    return fit, excluded, fit_years


def _selection(
    value: object, target_year: int
) -> tuple[tuple[int, ...], dict[Method, dict[int, tuple[int, int]]]]:
    payload = _keys(value, _SELECTION_KEYS, "selection")
    comparison = _years(payload["comparison_years"], "selection.comparison_years", target_year)
    flat_payload = _keys(payload["flat"], frozenset(METHODS), "selection.flat")
    flat: dict[Method, dict[int, tuple[int, int]]] = {}
    for method in METHODS:
        years = flat_payload[method]
        if not isinstance(years, dict) or sorted(years) != sorted(str(y) for y in comparison):
            raise ValueError("selection.flat must cover exactly the comparison years")
        flat[method] = {}
        for year in comparison:
            item = _keys(years[str(year)], _FLAT_KEYS, "selection.flat")
            flat[method][year] = (
                _integer(item["receipt_yen"], "selection.flat.receipt_yen", minimum=0),
                _integer(item["stake_yen"], "selection.flat.stake_yen", minimum=0),
            )
    return comparison, flat


def _sources(value: object) -> dict[str, object]:
    payload = _keys(value, _SOURCE_KEYS, "sources")
    _hex64(payload["backtest_report_sha256"], "sources.backtest_report_sha256")
    pl = _keys(payload["pl_evaluation"], _PL_SOURCE_KEYS, "sources.pl_evaluation")
    _hex64(pl["report_sha256"], "sources.pl_evaluation.report_sha256")
    _hex64(pl["predictions_sha256"], "sources.pl_evaluation.predictions_sha256")
    if not isinstance(pl["variant"], str) or not pl["variant"]:
        raise ValueError("sources.pl_evaluation.variant must be a nonempty string")
    snapshot = _keys(payload["snapshot"], _SNAPSHOT_KEYS, "sources.snapshot")
    if not isinstance(snapshot["snapshot_id"], str) or not _SNAPSHOT_ID.fullmatch(
        snapshot["snapshot_id"]
    ):
        raise ValueError("sources.snapshot.snapshot_id must be a snapshot name")
    tables = snapshot["tables"]
    if not isinstance(tables, dict) or not tables:
        raise ValueError("sources.snapshot.tables must be a non-empty object")
    for name, digest in tables.items():
        _hex64(digest, f"sources.snapshot.tables.{name}")
    return payload


def _years(value: object, name: str, target_year: int) -> tuple[int, ...]:
    if not isinstance(value, list):
        raise ValueError(f"betting estimator {name} must be a list")
    years = tuple(_integer(item, name, minimum=1) for item in value)
    if any(right <= left for left, right in pairwise(years)):
        raise ValueError(f"betting estimator {name} must increase strictly")
    if years and years[-1] >= target_year:
        raise ValueError(f"betting estimator {name} must precede target_year")
    return years


def _keys(value: object, expected: frozenset[str], where: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"betting estimator {where} keys differ from the format")
    return cast(dict[str, object], value)


def _integer(value: object, name: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"betting estimator {name} must be an integer of at least {minimum}")
    return value


def _number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"betting estimator {name} must be a finite number")
    return float(value)


def _optional_number(value: object, name: str) -> float | None:
    return None if value is None else _number(value, name)


def _numbers(value: object, name: str) -> tuple[float, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"betting estimator {name} must be a non-empty list")
    return tuple(_number(item, name) for item in value)


def _hex64(value: object, name: str) -> None:
    if not isinstance(value, str) or not _HEX64.fullmatch(value):
        raise ValueError(f"betting estimator {name} must be 64 lowercase hex digits")


def require_storable_width_bands(bands: tuple[float, ...]) -> None:
    """Require width bands that the artifact can store as whole tenths.

    Raises:
        ValueError: If a band edge is not a multiple of 0.1.
    """
    for edge in validate_width_bands(bands):
        _tenths(edge)


def _all_hits(correction: FinalOddsCorrection) -> int:
    fallback = correction.quantile_fallback
    assert fallback is not None  # decoded graded corrections always fall back
    return sum(band.hit_count for band in fallback.bands)


def _tenths(value: Fraction) -> int:
    tenths = value * 10
    if tenths.denominator != 1:
        raise ValueError("width band edges must be multiples of 0.1")
    return tenths.numerator


def _reject_constant(value: str) -> object:
    raise ValueError(f"betting estimator manifest must not contain {value}")


__all__ = [
    "BLEND_EXCLUSIONS",
    "FORMAT",
    "FORMAT_VERSION",
    "MANIFEST_FILE",
    "BettingEstimator",
    "BettingEstimatorRecord",
    "EstimatorSettings",
    "manifest_from_record",
    "read_betting_estimator",
    "record_from_manifest",
    "require_storable_width_bands",
    "write_betting_estimator",
]
