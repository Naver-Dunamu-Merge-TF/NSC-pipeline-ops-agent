from __future__ import annotations

from datetime import datetime, timezone
import logging

from orchestrator.pipeline_monitoring_config import (
    PipelineMonitoringConfig,
    load_pipeline_monitoring_config,
)
from orchestrator.utils.config import RuntimeSettings, load_runtime_settings
from orchestrator.utils.time import KST

_LOGGER = logging.getLogger(__name__)


def _is_daily_batch_poll_due(*, poll_after_kst: str, now_utc: datetime) -> bool:
    now_kst = now_utc.astimezone(KST)
    current_hhmm = now_kst.strftime("%H:%M")
    return current_hhmm >= poll_after_kst


def _is_microbatch_poll_due(*, poll_every_minutes: int, now_utc: datetime) -> bool:
    return now_utc.minute % poll_every_minutes == 0


def pipelines_to_poll(
    *,
    target_pipelines: list[str],
    now_utc: datetime,
    monitoring_config: PipelineMonitoringConfig | None = None,
) -> list[str]:
    config = monitoring_config or load_pipeline_monitoring_config()
    selected: list[str] = []

    for pipeline in target_pipelines:
        if pipeline == "pipeline_a":
            if _is_microbatch_poll_due(
                poll_every_minutes=config.pipelines.pipeline_a.poll_every_minutes,
                now_utc=now_utc,
            ):
                selected.append(pipeline)
            continue

        daily_config = getattr(config.pipelines, pipeline, None)
        if daily_config is None:
            _LOGGER.warning("Unknown target pipeline skipped: %s", pipeline)
            continue

        poll_after_kst = getattr(daily_config, "poll_after_kst", None)
        if not isinstance(poll_after_kst, str):
            continue

        if _is_daily_batch_poll_due(poll_after_kst=poll_after_kst, now_utc=now_utc):
            selected.append(pipeline)

    return selected


def run_once(
    *,
    now_utc: datetime | None = None,
    settings: RuntimeSettings | None = None,
    monitoring_config: PipelineMonitoringConfig | None = None,
) -> dict[str, list[str]]:
    runtime_settings = settings or load_runtime_settings()
    current_time = now_utc or datetime.now(timezone.utc)
    polled = pipelines_to_poll(
        target_pipelines=runtime_settings.target_pipelines,
        now_utc=current_time,
        monitoring_config=monitoring_config,
    )
    _LOGGER.info(
        "watchdog heartbeat: normal target=%s polled=%s",
        runtime_settings.target_pipelines,
        polled,
    )
    return {
        "target_pipelines": runtime_settings.target_pipelines,
        "polled_pipelines": polled,
    }
