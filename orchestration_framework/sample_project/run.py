"""
Entry point for Task Scheduler.

Task Scheduler action:
    Program:   python.exe
    Arguments: C:\\projects\\sample_project\\run.py
    Trigger:   Daily, 1:00 AM
"""

import config
import pipeline  # noqa: F401 — import registers all assets via the decorator
from framework import Orchestrator
from framework import lineage

if __name__ == "__main__":
    orch = Orchestrator(
        conn_str=config.SQL_CONN_STR,
        pipeline_name="aml_daily_report",
        description="Daily AML transaction report: Oracle + parquet -> SQL -> Power BI"
    )

    orch.materialize_all(triggered_by="Task Scheduler")

    # Regenerate the lineage diagram, colored by this run's outcome.
    # Crucial data (status, timing, errors) already lives in SQL via
    # orch.run / orch.asset_run — this step only reads it back to draw.
    statuses = orch.latest_statuses()
    lineage.draw_lineage(
        status_by_asset=statuses,
        output_path="lineage.png",
        title="aml_daily_report — latest run"
    )
