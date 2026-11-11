"""Tests for the Typer data CLI."""

import json
from datetime import date
from unittest.mock import Mock, patch

import pytest
from rich.text import Text
from typer.testing import CliRunner

from domain.race_key import RaceKey
from jra_van_retriever.acquisition.acquisition_lock import AcquisitionBlocked
from jra_van_retriever.acquisition.jvlink_runner import JVLinkToSQLiteError
from jra_van_retriever.acquisition.odds_archive import CaptureResult
from jra_van_retriever.retriever import JraVanRetriever
from jra_van_retriever.workflows.historical_odds import WeeklyBatchResult
from jra_van_retriever.workflows.race_day_odds import (
    CaptureReport,
    RaceDayOddsRunResult,
    RaceDayOddsSetupError,
)
from main import app

runner = CliRunner()


@pytest.fixture(params=[False, True], ids=["default-color", "forced-color"])
def cli_color_mode(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    if request.param:
        monkeypatch.setenv("FORCE_COLOR", "1")
        monkeypatch.setenv("TERM", "xterm-256color")
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.delenv("TTY_COMPATIBLE", raising=False)


@pytest.mark.parametrize(
    "command",
    [
        [],
        ["preprocess"],
        ["preprocess", "rebuild"],
        ["model"],
        ["model", "features"],
        ["model", "walk-forward"],
        ["model", "train"],
        ["model", "predict"],
        ["model", "prepare-input"],
        ["datamart"],
        ["datamart", "build-reference"],
    ],
)
def test_help_never_reads_inputs_or_creates_runtime_dependencies(command: list[str]) -> None:
    with (
        patch(
            "cli.json_io.read_json", side_effect=AssertionError("unexpected input read")
        ) as reader,
        patch(
            "cli.jra_van_retriever.DataRetriever.from_toml",
            side_effect=AssertionError("unexpected retriever"),
        ) as retriever,
        patch(
            "data.storage.snapshot_builder.SnapshotBuilder.from_toml",
            side_effect=AssertionError("unexpected preprocesser"),
        ) as preprocesser,
        patch(
            "cli.jra_van_retriever.JVLinkConfig.from_toml",
            side_effect=AssertionError("unexpected config read"),
        ) as config,
        patch(
            "cli.reference_datamart.load_reference_datamart_config",
            side_effect=AssertionError("unexpected reference datamart config read"),
        ) as datamart_config,
        patch(
            "cli.reference_datamart.FixedSnapshot",
            side_effect=AssertionError("unexpected fixed snapshot"),
        ) as fixed_snapshot,
    ):
        result = runner.invoke(app, [*command, "--help"])

    assert result.exit_code == 0
    reader.assert_not_called()
    retriever.assert_not_called()
    preprocesser.assert_not_called()
    config.assert_not_called()
    datamart_config.assert_not_called()
    fixed_snapshot.assert_not_called()


def test_historical_basic_cli_retrieves_then_rebuilds_processed_data() -> None:
    retriever = Mock()
    retriever.retrieve_historical_basic.side_effect = lambda publisher: publisher()
    preprocesser = Mock()
    preprocesser.rebuild.return_value = {"NL_RA_RACE": 100}
    with (
        patch("cli.jra_van_retriever.DataRetriever.from_toml", return_value=retriever) as from_toml,
        patch("data.storage.snapshot_builder.SnapshotBuilder.from_toml", return_value=preprocesser),
    ):
        result = runner.invoke(app, ["--retrieve", "--mode=historical-basic"])

    assert result.exit_code == 0
    assert "historical basic data retrieved" in result.stdout
    retriever.retrieve_historical_basic.assert_called_once()
    preprocesser.rebuild.assert_called_once_with()
    kwargs = from_toml.call_args.kwargs
    assert kwargs["data_config"].as_posix() == "configs/data.toml"
    assert kwargs["jvlink_config"].as_posix() == "configs/jvlink.toml"


def test_latest_cli_retrieves_then_refreshes_processed_data() -> None:
    retriever = Mock()
    preprocesser = Mock()
    preprocesser.update.return_value = {"NL_RA_RACE": 100}
    with (
        patch("cli.jra_van_retriever.DataRetriever.from_toml", return_value=retriever),
        patch("data.storage.snapshot_builder.SnapshotBuilder.from_toml", return_value=preprocesser),
    ):
        result = runner.invoke(app, ["--retrieve", "--mode=latest"])

    assert result.exit_code == 0
    retriever.retrieve_latest.assert_called_once_with()
    preprocesser.update.assert_called_once_with()


def test_historical_odds_cli_plan_only_is_forwarded() -> None:
    retriever = Mock()
    retriever.retrieve_historical_odds.return_value = WeeklyBatchResult(
        "plan", 2008, None, 4, 8, 0, 8, {}, True
    )
    with patch(
        "cli.jra_van_retriever.DataRetriever.from_toml", return_value=retriever
    ) as from_toml:
        result = runner.invoke(
            app,
            ["--retrieve", "--mode=historical-odds", "--plan-only"],
        )

    assert result.exit_code == 0
    assert '"year": 2008' in result.stdout
    retriever.retrieve_historical_odds.assert_called_once_with(plan_only=True, raw_only=True)
    assert from_toml.call_args.kwargs["create_runtime"] is False
    assert from_toml.call_args.kwargs["validate_executable"] is False


def test_historical_odds_cli_publishes_once_after_all_years_complete() -> None:
    retriever = Mock()
    retriever.retrieve_historical_odds.side_effect = [
        WeeklyBatchResult("completed", 2008, "run", 4, 8, 0, 0, {}),
        WeeklyBatchResult("completed", 2009, "run-2009", 5, 10, 0, 0, {}),
        WeeklyBatchResult("up_to_date", None, None, 0, 0, 0, 0, {}),
    ]
    preprocesser = Mock()
    preprocesser.rebuild.return_value = {"NL_RA_RACE": 100}
    retriever.publish_historical_odds.side_effect = lambda publisher: publisher()
    with (
        patch("cli.jra_van_retriever.DataRetriever.from_toml", return_value=retriever),
        patch("data.storage.snapshot_builder.SnapshotBuilder.from_toml", return_value=preprocesser),
    ):
        result = runner.invoke(app, ["--retrieve", "--mode=historical-odds"])

    assert result.exit_code == 0
    assert "Parquet publication is deferred" in result.stdout
    assert "Complete Parquet rebuild completed: 1 tables published." in result.stdout
    assert (
        "Starting complete Parquet rebuild after all historical odds are acquired." in result.stdout
    )
    assert retriever.retrieve_historical_odds.call_count == 3
    retriever.publish_historical_odds.assert_called_once()
    assert preprocesser.rebuild.call_count == 1


def test_historical_odds_cli_returns_failure_for_failed_batch() -> None:
    retriever = Mock()
    retriever.retrieve_historical_odds.return_value = WeeklyBatchResult(
        "failed", 2008, "run", 1, 2, 2, 2, {}
    )
    with patch("cli.jra_van_retriever.DataRetriever.from_toml", return_value=retriever):
        result = runner.invoke(app, ["--retrieve", "--mode=historical-odds"])

    assert result.exit_code == 1
    assert '"status": "failed"' in result.stdout


def test_historical_odds_cli_confirms_explicit_provider_missing_race() -> None:
    retriever = Mock()
    retriever.confirm_historical_odds_provider_missing.return_value = 2
    with patch("cli.jra_van_retriever.DataRetriever.from_toml", return_value=retriever):
        result = runner.invoke(
            app,
            [
                "--retrieve",
                "--mode=historical-odds",
                "--confirm-provider-missing",
                "--date",
                "2008-02-03",
                "--jyo",
                "05",
                "--kaiji",
                "01",
                "--nichiji",
                "02",
                "--race",
                "01",
            ],
        )

    assert result.exit_code == 0
    retriever.confirm_historical_odds_provider_missing.assert_called_once_with(
        RaceKey(date(2008, 2, 3), "05", "01", "02", "01"), frozenset({"0B41", "0B42"})
    )
    assert '"status": "provider_missing"' in result.stdout


def test_realtime_cli_retrieves_then_publishes_race_parquet() -> None:
    retriever = Mock()
    retriever.retrieve_realtime.return_value = 17
    preprocesser = Mock()
    preprocesser.update_race.return_value = {
        "ARCHIVE_O1_ODDS_TANFUKUWAKU": 10,
        "ARCHIVE_O2_ODDS_UMAREN": 7,
    }
    with (
        patch("cli.jra_van_retriever.DataRetriever.from_toml", return_value=retriever),
        patch("data.storage.snapshot_builder.SnapshotBuilder.from_toml", return_value=preprocesser),
    ):
        result = runner.invoke(
            app,
            [
                "--retrieve",
                "--mode=realtime",
                "--date",
                "2026-10-04",
                "--jyo",
                "05",
                "--kaiji",
                "04",
                "--nichiji",
                "08",
                "--race",
                "11",
            ],
        )

    assert result.exit_code == 0
    assert "17 rows" in result.stdout
    retriever.retrieve_realtime.assert_called_once_with(
        race_date=date(2026, 10, 4),
        jyo_code="05",
        kaiji="04",
        nichiji="08",
        race_number="11",
    )
    preprocesser.update_race.assert_called_once_with(
        RaceKey(date(2026, 10, 4), "05", "04", "08", "11")
    )


def test_realtime_cli_uses_race_config_when_options_are_omitted() -> None:
    retriever = Mock()
    retriever.retrieve_realtime.return_value = 17
    preprocesser = Mock()
    preprocesser.update_race.return_value = {
        "ARCHIVE_O1_ODDS_TANFUKUWAKU": 10,
        "ARCHIVE_O2_ODDS_UMAREN": 7,
    }
    race_key = RaceKey(date(2026, 10, 4), "05", "04", "08", "11")
    with (
        patch(
            "cli.jra_van_retriever.JVLinkConfig.from_toml",
            return_value=Mock(realtime_race=race_key),
        ),
        patch("cli.jra_van_retriever.DataRetriever.from_toml", return_value=retriever),
        patch("data.storage.snapshot_builder.SnapshotBuilder.from_toml", return_value=preprocesser),
    ):
        result = runner.invoke(app, ["--retrieve", "--mode=realtime"])

    assert result.exit_code == 0
    retriever.retrieve_realtime.assert_called_once_with(
        race_date=date(2026, 10, 4),
        jyo_code="05",
        kaiji="04",
        nichiji="08",
        race_number="11",
    )
    preprocesser.update_race.assert_called_once_with(race_key)


def test_retrieve_subcommand_is_removed() -> None:
    result = runner.invoke(app, ["retrieve", "historical"])

    assert result.exit_code == 2


def test_legacy_historical_mode_names_are_rejected() -> None:
    for mode in ("historical", "historical-weekly"):
        result = runner.invoke(app, ["--retrieve", f"--mode={mode}"])

        assert result.exit_code == 2


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (["--plan-only", "--recover"], "retrieval options require"),
        (
            ["--retrieve", "--plan-only", "--recover", "model"],
            "retrieval options cannot be used with a subcommand",
        ),
        (
            ["--mode=unknown", "--plan-only", "--recover"],
            "--plan-only cannot be combined with --recover",
        ),
        (
            ["--retrieve", "--mode=unknown", "--confirm-provider-missing", "--recover"],
            "--confirm-provider-missing cannot be combined",
        ),
        (
            ["--retrieve", "--mode=realtime", "--date=2026-01-01", "--plan-only"],
            "odds-only options require",
        ),
        (
            ["--retrieve", "--mode=historical-odds", "--date=2026-01-01"],
            "require --confirm-provider-missing",
        ),
    ],
)
@pytest.mark.usefixtures("cli_color_mode")
def test_retrieval_option_errors_preserve_validation_priority(
    arguments: list[str], message: str
) -> None:
    with (
        patch("cli.jra_van_retriever.DataRetriever.from_toml") as retriever,
        patch("data.storage.snapshot_builder.SnapshotBuilder.from_toml") as preprocesser,
        patch("cli.jra_van_retriever.JVLinkConfig.from_toml") as config,
    ):
        result = runner.invoke(app, arguments)

    assert result.exit_code == 2
    output = Text.from_ansi(result.output).plain
    assert message in " ".join(output.replace("│", "").split())
    retriever.assert_not_called()
    preprocesser.assert_not_called()
    config.assert_not_called()


@pytest.mark.parametrize("mode", ["historical-basic", "latest"])
@pytest.mark.parametrize("option", ["--recover", "--jyo=05", "--data-spec=0B41"])
def test_non_odds_modes_reject_odds_and_race_options(mode: str, option: str) -> None:
    with patch("cli.jra_van_retriever.DataRetriever.from_toml") as retriever:
        result = runner.invoke(app, ["--retrieve", f"--mode={mode}", option])

    assert result.exit_code == 2
    assert "odds-only options require" in result.output
    retriever.assert_not_called()


@pytest.mark.parametrize(
    "race_option", ["--date=2026-01-01", "--jyo=05", "--kaiji=01", "--nichiji=01", "--race=01"]
)
def test_realtime_partial_race_never_falls_back_to_configuration(race_option: str) -> None:
    with (
        patch("cli.jra_van_retriever.JVLinkConfig.from_toml") as config,
        patch("cli.jra_van_retriever.DataRetriever.from_toml") as retriever,
    ):
        result = runner.invoke(app, ["--retrieve", "--mode=realtime", race_option])

    assert result.exit_code == 2
    assert "realtime CLI options must include" in result.output
    config.assert_not_called()
    retriever.assert_not_called()


@pytest.mark.usefixtures("cli_color_mode")
def test_provider_confirmation_requires_explicit_race_before_validating_specs() -> None:
    with (
        patch("cli.jra_van_retriever.JVLinkConfig.from_toml") as config,
        patch("cli.jra_van_retriever.DataRetriever.from_toml") as retriever,
    ):
        result = runner.invoke(
            app,
            [
                "--retrieve",
                "--mode=historical-odds",
                "--confirm-provider-missing",
                "--data-spec=invalid",
            ],
        )

    assert result.exit_code == 2
    assert "--confirm-provider-missing requires" in Text.from_ansi(result.output).plain
    config.assert_not_called()
    retriever.assert_not_called()


@pytest.mark.parametrize("confirm", [False, True])
def test_invalid_complete_race_retains_mode_specific_error_translation(confirm: bool) -> None:
    arguments = ["--retrieve", f"--mode={'historical-odds' if confirm else 'realtime'}"]
    if confirm:
        arguments.append("--confirm-provider-missing")
    arguments.extend(
        ["--date=2026-01-01", "--jyo=invalid", "--kaiji=01", "--nichiji=01", "--race=01"]
    )
    with patch("cli.jra_van_retriever.DataRetriever.from_toml") as retriever:
        result = runner.invoke(app, arguments)

    if confirm:
        assert result.exit_code == 2
        assert "invalid provider-missing RaceKey" in result.output
    else:
        assert result.exit_code == 1
        assert isinstance(result.exception, ValueError)
        assert "jyo_code must be a two-digit string" in str(result.exception)
    retriever.assert_not_called()


def test_preprocess_rebuild_can_run_without_retrieval() -> None:
    preprocesser = Mock()
    preprocesser.rebuild.return_value = {"NL_RA_RACE": 100}
    with patch(
        "data.storage.snapshot_builder.SnapshotBuilder.from_toml", return_value=preprocesser
    ):
        result = runner.invoke(app, ["preprocess", "rebuild"])

    assert result.exit_code == 0
    preprocesser.rebuild.assert_called_once_with()


def _race_day_result(failed: int) -> Mock:
    report = CaptureReport(
        "abc",
        RaceKey(date(2026, 11, 15), "05", "05", "04", "11"),
        5,
        {"0B31": CaptureResult("archived", "capture_archive_committed")},
    )
    summary = {"archived": 1, "no_data": 0, "failed": failed, "skipped_late": 0, "interrupted": 0}
    retriever = Mock()

    def retrieve(
        race_date: date, *, reporter: object, recovery_reporter: object
    ) -> RaceDayOddsRunResult:
        assert race_date == date(2026, 11, 15)
        recovery_reporter(0)  # type: ignore[operator]
        reporter(report)  # type: ignore[operator]
        return RaceDayOddsRunResult((report,), summary)

    retriever.retrieve_race_day_odds.side_effect = retrieve
    return retriever


@pytest.mark.parametrize(("failed", "exit_code"), [(0, 0), (1, 1)])
def test_race_day_odds_cli_reports_each_capture_then_summary(failed: int, exit_code: int) -> None:
    retriever = _race_day_result(failed)
    with patch("cli.jra_van_retriever.DataRetriever.from_toml", return_value=retriever):
        result = runner.invoke(app, ["--retrieve", "--mode=race-day-odds", "--date=2026-11-15"])

    assert result.exit_code == exit_code
    lines = result.stdout.strip().splitlines()
    assert lines[0] == "race-day-odds capture abc 2026-11-15/05/05/04/11 -5m 0B31=archived"
    assert json.loads(lines[-1]) == {
        "archived": 1,
        "no_data": 0,
        "failed": failed,
        "skipped_late": 0,
        "interrupted": 0,
    }


def test_race_day_odds_cli_exits_130_on_interrupt_with_recovery_count() -> None:
    def retrieve(race_date: date, *, reporter: object, recovery_reporter: object) -> None:
        recovery_reporter(6)  # type: ignore[operator]
        raise KeyboardInterrupt

    retriever = Mock()
    retriever.retrieve_race_day_odds.side_effect = retrieve
    with patch("cli.jra_van_retriever.DataRetriever.from_toml", return_value=retriever):
        result = runner.invoke(app, ["--retrieve", "--mode=race-day-odds", "--date=2026-11-15"])

    assert result.exit_code == 130
    summary = json.loads(result.stdout.strip().splitlines()[-1])
    assert (summary["failed"], summary["interrupted"]) == (0, 6)


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ([], "race-day-odds requires --date"),
        (["--date=2026-11-15", "--jyo=05"], "accepts --date but not"),
        (["--date=2026-11-15", "--race=11"], "accepts --date but not"),
        (["--date=2026-11-15", "--plan-only"], "odds-only options require"),
        (["--date=2026-11-15", "--data-spec=0B31"], "odds-only options require"),
        (["--date=2026-11-15", "--confirm-provider-missing"], "odds-only options require"),
        (["--recover", "--date=2026-11-15"], "--recover does not accept"),
        (["--recover", "--jyo=05"], "--recover does not accept"),
        (["--recover", "--race=11"], "--recover does not accept"),
        (["--recover", "--data-spec=0B31"], "odds-only options require"),
    ],
)
@pytest.mark.usefixtures("cli_color_mode")
def test_race_day_odds_cli_rejects_invalid_options(arguments: list[str], message: str) -> None:
    with patch("cli.jra_van_retriever.DataRetriever.from_toml") as retriever:
        result = runner.invoke(app, ["--retrieve", "--mode=race-day-odds", *arguments])

    assert result.exit_code == 2
    output = Text.from_ansi(result.output).plain
    assert message in " ".join(output.replace("│", "").split())
    retriever.assert_not_called()


@pytest.mark.usefixtures("cli_color_mode")
def test_unknown_mode_lists_race_day_odds() -> None:
    result = runner.invoke(app, ["--retrieve", "--mode=unknown"])

    assert result.exit_code == 2
    output = " ".join(Text.from_ansi(result.output).plain.replace("│", "").split())
    assert "'race-day-odds'" in output


def test_race_day_odds_requires_configured_section() -> None:
    retriever = JraVanRetriever.__new__(JraVanRetriever)
    retriever._race_day_odds = None

    with pytest.raises(ValueError, match=r"\[race_day_odds\] is required"):
        retriever.retrieve_race_day_odds(date(2026, 11, 15))


def test_race_day_odds_recover_only_recovers_and_reports_the_count() -> None:
    retriever = Mock()
    retriever.recover_race_day_odds.return_value = 6
    with patch("cli.jra_van_retriever.DataRetriever.from_toml", return_value=retriever):
        result = runner.invoke(app, ["--retrieve", "--mode=race-day-odds", "--recover"])

    assert result.exit_code == 0
    assert json.loads(result.stdout.strip().splitlines()[-1]) == {"interrupted": 6}
    retriever.recover_race_day_odds.assert_called_once_with()
    retriever.retrieve_race_day_odds.assert_not_called()


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (
            AcquisitionBlocked("another acquisition process\nholds the raw database lock"),
            "another acquisition process holds the raw database lock",
        ),
        (
            JVLinkToSQLiteError("JVLinkToSQLite is still running"),
            "JVLinkToSQLite is still running",
        ),
    ],
    ids=["lock_held", "runner_running"],
)
def test_race_day_odds_recover_failure_exits_1_with_one_stderr_line(
    error: Exception, message: str
) -> None:
    retriever = Mock()
    retriever.recover_race_day_odds.side_effect = error
    with patch("cli.jra_van_retriever.DataRetriever.from_toml", return_value=retriever):
        result = runner.invoke(app, ["--retrieve", "--mode=race-day-odds", "--recover"])

    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr == f"race-day-odds recovery failed: {message}\n"


def test_race_day_odds_setup_error_exits_1_with_message_and_summary() -> None:
    def retrieve(race_date: date, *, reporter: object, recovery_reporter: object) -> None:
        recovery_reporter(2)  # type: ignore[operator]
        raise RaceDayOddsSetupError("race-day-odds execution setting is invalid: no JVRaceKey")

    retriever = Mock()
    retriever.retrieve_race_day_odds.side_effect = retrieve
    with patch("cli.jra_van_retriever.DataRetriever.from_toml", return_value=retriever):
        result = runner.invoke(app, ["--retrieve", "--mode=race-day-odds", "--date=2026-11-15"])

    assert result.exit_code == 1
    assert result.stderr == (
        "race-day-odds setup failed: race-day-odds execution setting is invalid: no JVRaceKey\n"
    )
    assert json.loads(result.stdout.strip().splitlines()[-1]) == {
        "archived": 0,
        "no_data": 0,
        "failed": 0,
        "skipped_late": 0,
        "interrupted": 2,
    }


def test_race_day_odds_recover_requires_configured_section() -> None:
    retriever = JraVanRetriever.__new__(JraVanRetriever)
    retriever._race_day_odds = None

    with pytest.raises(ValueError, match=r"\[race_day_odds\] is required"):
        retriever.recover_race_day_odds()
