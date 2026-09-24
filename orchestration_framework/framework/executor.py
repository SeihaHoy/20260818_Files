"""
Executor — runs registered assets in dependency order and persists
every step to SQL Server (orch.run / orch.asset_run / orch.run_log).

This is the piece Task Scheduler actually calls: one Orchestrator,
one materialize_all() per run.
"""

from .core import topological_order
from . import db


class Orchestrator:
    def __init__(self, conn_str, pipeline_name, description=""):
        self.conn_str = conn_str
        self.pipeline_name = pipeline_name
        self.description = description

    def materialize_all(self, triggered_by="Task Scheduler"):
        assets = topological_order()

        conn = db.get_connection(self.conn_str)
        pipeline_id = db.get_or_create_pipeline(conn, self.pipeline_name, self.description)
        asset_ids = db.sync_assets(conn, pipeline_id, assets)
        run_id = db.start_run(conn, pipeline_id, triggered_by)

        failed = False
        for a in assets:
            asset_id = asset_ids[a.name]

            if failed:
                # An upstream asset already failed this run — mark the
                # rest skipped rather than silently not running them.
                db.skip_asset_run(conn, run_id, asset_id)
                print(f"[{a.name}] skipped (upstream failure)")
                continue

            asset_run_id = db.start_asset_run(conn, run_id, asset_id)
            print(f"[{a.name}] materializing...")
            try:
                result = a.func()
                a.result = result
                rows = len(result) if hasattr(result, "__len__") else None
                db.finish_asset_run(conn, asset_run_id, "success", rows_processed=rows)
                print(f"[{a.name}] success" + (f" ({rows} rows)" if rows is not None else ""))
            except Exception as e:
                db.finish_asset_run(conn, asset_run_id, "failed", error_message=str(e))
                db.log(conn, asset_run_id, str(e), level="ERROR")
                print(f"[{a.name}] FAILED: {e}")
                failed = True

        db.finish_run(conn, run_id, "failed" if failed else "success")
        conn.close()

        print(f"\nRun {run_id} finished: {'failed' if failed else 'success'}")
        return run_id

    def latest_statuses(self):
        """Fetch {asset_name: status} for the most recent run — used by lineage.py."""
        conn = db.get_connection(self.conn_str)
        pipeline_id = db.get_or_create_pipeline(conn, self.pipeline_name, self.description)
        statuses = db.get_latest_statuses(conn, pipeline_id)
        conn.close()
        return statuses
