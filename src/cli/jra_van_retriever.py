"""Validate retrieval options and execute acquisition commands."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Annotated

import typer

from cli.options import DataConfigOption, JVLinkConfigOption
from data.storage.snapshot_builder import SnapshotBuilder
from domain.race_key import RaceKey
from jra_van_retriever.acquisition.acquisition_lock import AcquisitionBlocked
from jra_van_retriever.acquisition.jvlink_runner import JVLinkToSQLiteError
from jra_van_retriever.config.profiles import JVLinkConfig
from jra_van_retriever.retriever import DataRetriever
from jra_van_retriever.workflows.race_day_odds import CaptureReport, RaceDayOddsSetupError


@dataclass(frozen=True)
class _RaceOptions:
    race_datetime: datetime | None
    jyo_code: str | None
    kaiji: str | None
    nichiji: str | None
    race_number: str | None

    @property
    def specified(self) -> bool:
        return any(
            value is not None
            for value in (
                self.race_datetime,
                self.jyo_code,
                self.kaiji,
                self.nichiji,
                self.race_number,
            )
        )

    def require_complete(self, message: str) -> RaceKey:
        if (
            self.race_datetime is None
            or self.jyo_code is None
            or self.kaiji is None
            or self.nichiji is None
            or self.race_number is None
        ):
            raise typer.BadParameter(message)
        return RaceKey(
            self.race_datetime.date(), self.jyo_code, self.kaiji, self.nichiji, self.race_number
        )


def main(
    ctx: typer.Context,
    retrieve: Annotated[
        bool,
        typer.Option("--retrieve", help="Run a retrieval workflow selected by --mode."),
    ] = False,
    mode: Annotated[
        str | None,
        typer.Option("--mode", help="Retrieval mode for the flag-based interface."),
    ] = None,
    plan_only: Annotated[
        bool,
        typer.Option("--plan-only", help="Inspect a historical-odds plan without writing."),
    ] = False,
    recover: Annotated[
        bool,
        typer.Option(
            "--recover",
            help=(
                "Quarantine and recover an interrupted historical-odds request "
                "or race-day-odds capture."
            ),
        ),
    ] = False,
    confirm_provider_missing: Annotated[
        bool,
        typer.Option(
            "--confirm-provider-missing",
            help="Confirm a failed empty response as a JRA-VAN-side gap.",
        ),
    ] = False,
    data_spec: Annotated[
        list[str] | None,
        typer.Option("--data-spec", help="DataSpec to confirm; repeat for multiple specs."),
    ] = None,
    data_config: DataConfigOption = Path("configs/data.toml"),
    jvlink_config: JVLinkConfigOption = Path("configs/jvlink.toml"),
    race_datetime: Annotated[
        datetime | None,
        typer.Option("--date", formats=["%Y-%m-%d"], help="Race date (YYYY-MM-DD)."),
    ] = None,
    jyo_code: Annotated[str | None, typer.Option("--jyo", help="Two-digit JRA venue code.")] = None,
    kaiji: Annotated[str | None, typer.Option("--kaiji", help="Two-digit meeting number.")] = None,
    nichiji: Annotated[str | None, typer.Option("--nichiji", help="Two-digit meeting day.")] = None,
    race_number: Annotated[
        str | None, typer.Option("--race", help="Two-digit race number.")
    ] = None,
) -> None:
    """Run a retrieval workflow selected by the mode option."""
    race = _RaceOptions(race_datetime, jyo_code, kaiji, nichiji, race_number)
    odds_options = bool(plan_only or recover or confirm_provider_missing or data_spec)
    retrieval_options = odds_options or race.specified
    if ctx.invoked_subcommand is not None:
        if retrieve or mode is not None or retrieval_options:
            raise typer.BadParameter("retrieval options cannot be used with a subcommand")
        return

    if not retrieve and mode is None:
        if retrieval_options:
            raise typer.BadParameter("retrieval options require --retrieve --mode")
        return
    if plan_only and recover:
        raise typer.BadParameter("--plan-only cannot be combined with --recover")
    if confirm_provider_missing and (plan_only or recover):
        raise typer.BadParameter(
            "--confirm-provider-missing cannot be combined with --plan-only/--recover"
        )
    if not retrieve:
        raise typer.BadParameter("--mode requires --retrieve")
    if mode in {"historical-basic", "latest"}:
        if retrieval_options:
            raise typer.BadParameter("odds-only options require --mode historical-odds")
        if mode == "historical-basic":
            retrieve_historical_basic(data_config, jvlink_config)
        else:
            retrieve_latest(data_config, jvlink_config)
        return
    if mode == "historical-odds":
        if confirm_provider_missing:
            race_key = _require_provider_missing_race(race)
            specs = _provider_missing_specs(data_spec)
            confirm_historical_odds_provider_missing(race_key, specs, data_config, jvlink_config)
            return
        if race.specified or data_spec:
            raise typer.BadParameter(
                "race options and --data-spec require --confirm-provider-missing"
            )
        retrieve_historical_odds(data_config, jvlink_config, plan_only=plan_only, recover=recover)
        return
    if mode == "realtime":
        if odds_options:
            raise typer.BadParameter("odds-only options require --mode historical-odds")
        race_key = _resolve_realtime_race(jvlink_config, race)
        retrieve_realtime(race_key, data_config, jvlink_config)
        return
    if mode == "race-day-odds":
        if plan_only or confirm_provider_missing or data_spec:
            raise typer.BadParameter("odds-only options require --mode historical-odds")
        if recover:
            if race.specified:
                raise typer.BadParameter(
                    "race-day-odds --recover does not accept --date, --jyo, --kaiji, "
                    "--nichiji, or --race"
                )
            recover_race_day_odds(data_config, jvlink_config)
            return
        if race.race_datetime is None:
            raise typer.BadParameter("race-day-odds requires --date")
        if any(
            value is not None
            for value in (race.jyo_code, race.kaiji, race.nichiji, race.race_number)
        ):
            raise typer.BadParameter(
                "race-day-odds accepts --date but not --jyo, --kaiji, --nichiji, or --race"
            )
        retrieve_race_day_odds(race.race_datetime.date(), data_config, jvlink_config)
        return
    raise typer.BadParameter(
        "--mode must be 'historical-basic', 'historical-odds', 'latest', 'realtime', "
        "or 'race-day-odds'"
    )


def _retriever(data_config: Path, jvlink_config: Path, *, plan_only: bool = False) -> DataRetriever:
    if not plan_only:
        return DataRetriever.from_toml(data_config=data_config, jvlink_config=jvlink_config)
    return DataRetriever.from_toml(
        data_config=data_config,
        jvlink_config=jvlink_config,
        create_runtime=not plan_only,
        validate_executable=False,
    )


def _resolve_realtime_race(
    jvlink_config: Path,
    race: _RaceOptions,
) -> RaceKey:
    if race.specified:
        return race.require_complete(
            "realtime CLI options must include --date, --jyo, --kaiji, --nichiji, and --race"
        )

    configured_race = JVLinkConfig.from_toml(jvlink_config).realtime_race
    if configured_race is None:
        raise typer.BadParameter(
            "realtime requires CLI race options or a [realtime] section in the JVLink config"
        )
    return configured_race


def _require_provider_missing_race(race: _RaceOptions) -> RaceKey:
    """Require an explicit complete RaceKey for a provider-gap confirmation."""
    try:
        return race.require_complete(
            "--confirm-provider-missing requires --date, --jyo, --kaiji, --nichiji, and --race"
        )
    except ValueError as exc:
        raise typer.BadParameter(f"invalid provider-missing RaceKey: {exc}") from exc


def _provider_missing_specs(data_specs: list[str] | None) -> frozenset[str]:
    """Validate the explicitly confirmed realtime odds DataSpecs."""
    values = data_specs or ["0B41", "0B42"]
    if len(values) != len(set(values)) or not set(values) <= {"0B41", "0B42"}:
        raise typer.BadParameter("--data-spec accepts only unique 0B41 and 0B42 values")
    return frozenset(values)


def retrieve_historical_basic(
    data_config: DataConfigOption = Path("configs/data.toml"),
    jvlink_config: JVLinkConfigOption = Path("configs/jvlink.toml"),
) -> None:
    """Retrieve historical base data and publish a complete Parquet snapshot."""
    tables: dict[str, int] = {}

    def publish() -> None:
        tables.update(SnapshotBuilder.from_toml(data_config).rebuild())

    _retriever(data_config, jvlink_config).retrieve_historical_basic(publish)
    typer.echo("historical basic data retrieved")
    typer.echo(f"processed snapshot published: {len(tables)} tables")


def retrieve_historical_odds(
    data_config: DataConfigOption = Path("configs/data.toml"),
    jvlink_config: JVLinkConfigOption = Path("configs/jvlink.toml"),
    *,
    plan_only: bool = False,
    recover: bool = False,
) -> None:
    """Acquire historical odds years and publish one snapshot after raw completion."""
    retriever = _retriever(data_config, jvlink_config, plan_only=plan_only)
    recover_pending = recover
    while True:
        if recover_pending:
            result = retriever.retrieve_historical_odds(
                plan_only=plan_only, recover=True, raw_only=True
            )
        else:
            result = retriever.retrieve_historical_odds(plan_only=plan_only, raw_only=True)
        recover_pending = False
        if not plan_only and result.status == "completed" and result.year is not None:
            typer.echo(
                f"Historical odds raw acquisition completed for year {result.year}; "
                "Parquet publication is deferred until all years are acquired."
            )
            typer.echo(json.dumps(asdict(result), ensure_ascii=False, sort_keys=True))
            continue
        if not plan_only and result.status == "up_to_date":
            typer.echo("Starting complete Parquet rebuild after all historical odds are acquired.")
            try:
                tables = retriever.publish_historical_odds(
                    lambda: SnapshotBuilder.from_toml(data_config).rebuild()
                )
            except BaseException:
                typer.echo("Complete Parquet rebuild failed.", err=True)
                raise
            if tables is not None:
                typer.echo(f"Complete Parquet rebuild completed: {len(tables)} tables published.")
            typer.echo(json.dumps(asdict(result), ensure_ascii=False, sort_keys=True))
            return
        typer.echo(json.dumps(asdict(result), ensure_ascii=False, sort_keys=True))
        if result.status == "failed":
            raise typer.Exit(code=1)
        return


def confirm_historical_odds_provider_missing(
    race_key: RaceKey,
    specs: frozenset[str],
    data_config: DataConfigOption = Path("configs/data.toml"),
    jvlink_config: JVLinkConfigOption = Path("configs/jvlink.toml"),
) -> None:
    """Confirm selected empty-response failures without starting JV-Link."""
    count = _retriever(data_config, jvlink_config).confirm_historical_odds_provider_missing(
        race_key, specs
    )
    typer.echo(
        json.dumps(
            {
                "race": str(race_key),
                "data_specs": sorted(specs),
                "confirmed": count,
                "status": "provider_missing",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


def retrieve_latest(
    data_config: DataConfigOption = Path("configs/data.toml"),
    jvlink_config: JVLinkConfigOption = Path("configs/jvlink.toml"),
) -> None:
    """Retrieve latest raw data and refresh the complete Parquet snapshot."""
    _retriever(data_config, jvlink_config).retrieve_latest()
    tables = SnapshotBuilder.from_toml(data_config).update()
    typer.echo("latest race data retrieved")
    typer.echo(f"processed snapshot published: {len(tables)} tables")


def retrieve_realtime(
    race_key: RaceKey,
    data_config: Path,
    jvlink_config: Path,
) -> None:
    """Retrieve and publish prediction-time Parquet for one target race."""
    inserted = _retriever(data_config, jvlink_config).retrieve_realtime(
        race_date=race_key.race_date,
        jyo_code=race_key.jyo_code,
        kaiji=race_key.kaiji,
        nichiji=race_key.nichiji,
        race_number=race_key.race_number,
    )
    tables = SnapshotBuilder.from_toml(data_config).update_race(race_key)
    typer.echo(f"realtime odds archived: {inserted} rows")
    # Only the odds tables count; the race's capture log may be published too (ADR-037).
    odds = ("ARCHIVE_O1_ODDS_TANFUKUWAKU", "ARCHIVE_O2_ODDS_UMAREN")
    typer.echo(f"realtime Parquet published: {sum(tables.get(name, 0) for name in odds)} rows")


def retrieve_race_day_odds(
    race_date: date,
    data_config: Path,
    jvlink_config: Path,
) -> None:
    """Capture all configured pre-race odds observations for one date."""
    partial_summary = {
        "archived": 0,
        "no_data": 0,
        "failed": 0,
        "skipped_late": 0,
        "interrupted": 0,
    }

    def report(capture: CaptureReport) -> None:
        statuses = " ".join(
            f"{spec}={result.status}" for spec, result in sorted(capture.results.items())
        )
        for result in capture.results.values():
            partial_summary[result.status] += 1
        typer.echo(
            f"race-day-odds capture {capture.capture_id} {capture.race_key} "
            f"-{capture.offset_minutes}m {statuses}"
        )

    def recovered(count: int) -> None:
        partial_summary["interrupted"] += count

    try:
        # Each prediction fetch publishes its race's odds and log for the feature command.
        publisher = SnapshotBuilder.from_toml(data_config).update_race
        result = _retriever(data_config, jvlink_config).retrieve_race_day_odds(
            race_date, reporter=report, recovery_reporter=recovered, publisher=publisher
        )
    except KeyboardInterrupt:
        typer.echo(json.dumps(partial_summary, separators=(",", ":")))
        raise typer.Exit(code=130) from None
    except RaceDayOddsSetupError as exc:
        typer.echo(f"race-day-odds setup failed: {_one_line(exc)}", err=True)
        typer.echo(json.dumps(partial_summary, separators=(",", ":")))
        raise typer.Exit(code=1) from None
    typer.echo(json.dumps(result.summary, separators=(",", ":")))
    if result.failed:
        raise typer.Exit(code=1)


def recover_race_day_odds(data_config: Path, jvlink_config: Path) -> None:
    """Recover interrupted race-day captures without starting the capture loop."""
    try:
        interrupted = _retriever(data_config, jvlink_config).recover_race_day_odds()
    except (AcquisitionBlocked, JVLinkToSQLiteError) as exc:
        typer.echo(f"race-day-odds recovery failed: {_one_line(exc)}", err=True)
        raise typer.Exit(code=1) from None
    typer.echo(json.dumps({"interrupted": interrupted}, separators=(",", ":")))


def _one_line(error: BaseException) -> str:
    return " ".join(str(error).split())
