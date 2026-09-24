"""
SQL Server persistence layer.

Mirrors the orch.* schema (see sql/schema.sql). This module is the only
place that writes to those tables — the executor calls these functions,
it never runs raw SQL itself.
"""

import pyodbc


def get_connection(conn_str):
    return pyodbc.connect(conn_str)


def get_or_create_pipeline(conn, pipeline_name, description=""):
    cur = conn.cursor()
    cur.execute("SELECT pipeline_id FROM orch.pipeline WHERE pipeline_name = ?", pipeline_name)
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute(
        "INSERT INTO orch.pipeline (pipeline_name, description) "
        "OUTPUT INSERTED.pipeline_id VALUES (?, ?)",
        pipeline_name, description
    )
    pipeline_id = cur.fetchone()[0]
    conn.commit()
    return pipeline_id


def sync_assets(conn, pipeline_id, assets):
    """Insert-if-not-exists each asset and its dependency edges.

    Called at the start of every run so orch.asset / orch.asset_dependency
    always reflect the current code, even if assets were added or their
    deps changed since the last run. Returns {asset_name: asset_id}.
    """
    cur = conn.cursor()
    ids = {}
    for a in assets:
        cur.execute(
            "SELECT asset_id FROM orch.asset WHERE pipeline_id = ? AND asset_name = ?",
            pipeline_id, a.name
        )
        row = cur.fetchone()
        if row:
            ids[a.name] = row[0]
        else:
            cur.execute(
                "INSERT INTO orch.asset (pipeline_id, asset_name, asset_group, description, owner) "
                "OUTPUT INSERTED.asset_id VALUES (?, ?, ?, ?, ?)",
                pipeline_id, a.name, a.group, a.description, a.owner
            )
            ids[a.name] = cur.fetchone()[0]
    conn.commit()

    for a in assets:
        for dep in a.deps:
            cur.execute(
                "SELECT 1 FROM orch.asset_dependency WHERE asset_id = ? AND depends_on_asset_id = ?",
                ids[a.name], ids[dep.name]
            )
            if not cur.fetchone():
                cur.execute(
                    "INSERT INTO orch.asset_dependency (asset_id, depends_on_asset_id) VALUES (?, ?)",
                    ids[a.name], ids[dep.name]
                )
    conn.commit()
    return ids


def start_run(conn, pipeline_id, triggered_by="Task Scheduler"):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO orch.run (pipeline_id, triggered_by, status) "
        "OUTPUT INSERTED.run_id VALUES (?, ?, 'running')",
        pipeline_id, triggered_by
    )
    run_id = cur.fetchone()[0]
    conn.commit()
    return run_id


def finish_run(conn, run_id, status):
    cur = conn.cursor()
    cur.execute(
        "UPDATE orch.run SET end_time = SYSUTCDATETIME(), status = ? WHERE run_id = ?",
        status, run_id
    )
    conn.commit()


def start_asset_run(conn, run_id, asset_id):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO orch.asset_run (run_id, asset_id, start_time, status) "
        "OUTPUT INSERTED.asset_run_id VALUES (?, ?, SYSUTCDATETIME(), 'running')",
        run_id, asset_id
    )
    asset_run_id = cur.fetchone()[0]
    conn.commit()
    return asset_run_id


def finish_asset_run(conn, asset_run_id, status, rows_processed=None, error_message=None):
    cur = conn.cursor()
    cur.execute(
        "UPDATE orch.asset_run SET end_time = SYSUTCDATETIME(), status = ?, "
        "rows_processed = ?, error_message = ? WHERE asset_run_id = ?",
        status, rows_processed, error_message, asset_run_id
    )
    conn.commit()


def skip_asset_run(conn, run_id, asset_id):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO orch.asset_run (run_id, asset_id, status) VALUES (?, ?, 'skipped')",
        run_id, asset_id
    )
    conn.commit()


def log(conn, asset_run_id, message, level="INFO"):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO orch.run_log (asset_run_id, log_level, message) VALUES (?, ?, ?)",
        asset_run_id, level, message
    )
    conn.commit()


def get_latest_statuses(conn, pipeline_id):
    """Return {asset_name: status} for every asset's most recent run.

    Used by lineage.py to color the dependency graph by outcome.
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT a.asset_name, ar.status
        FROM orch.asset a
        JOIN orch.asset_run ar ON ar.asset_id = a.asset_id
        WHERE a.pipeline_id = ?
          AND ar.run_id = (SELECT MAX(run_id) FROM orch.run WHERE pipeline_id = ?)
        """,
        pipeline_id, pipeline_id
    )
    return {row[0]: row[1] for row in cur.fetchall()}
