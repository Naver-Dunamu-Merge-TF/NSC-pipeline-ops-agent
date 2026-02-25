from __future__ import annotations

from datetime import datetime, timezone
import logging

from orchestrator.utils.config import load_runtime_settings

from runtime import watchdog


def test_pipelines_to_poll_respects_daily_batch_poll_after_window() -> None:
    before_window = datetime(2026, 2, 25, 15, 9, tzinfo=timezone.utc)
    at_window = datetime(2026, 2, 25, 15, 10, tzinfo=timezone.utc)

    assert (
        watchdog.pipelines_to_poll(
            target_pipelines=["pipeline_silver"],
            now_utc=before_window,
        )
        == []
    )
    assert watchdog.pipelines_to_poll(
        target_pipelines=["pipeline_silver"],
        now_utc=at_window,
    ) == ["pipeline_silver"]


def test_pipelines_to_poll_applies_five_minute_rule_for_pipeline_a() -> None:
    not_due = datetime(2026, 2, 25, 0, 12, tzinfo=timezone.utc)
    due = datetime(2026, 2, 25, 0, 15, tzinfo=timezone.utc)

    assert (
        watchdog.pipelines_to_poll(
            target_pipelines=["pipeline_a"],
            now_utc=not_due,
        )
        == []
    )
    assert watchdog.pipelines_to_poll(
        target_pipelines=["pipeline_a"],
        now_utc=due,
    ) == ["pipeline_a"]


def test_run_once_uses_target_pipelines_from_runtime_settings(caplog) -> None:
    settings = load_runtime_settings(
        {
            "TARGET_PIPELINES": "pipeline_silver,pipeline_a",
            "LANGFUSE_HOST": "http://localhost:3000",
        }
    )

    with caplog.at_level(logging.INFO):
        result = watchdog.run_once(
            now_utc=datetime(2026, 2, 25, 15, 11, tzinfo=timezone.utc),
            settings=settings,
        )

    assert result["target_pipelines"] == ["pipeline_silver", "pipeline_a"]
    assert result["polled_pipelines"] == ["pipeline_silver"]
    assert "watchdog heartbeat: normal" in caplog.text
