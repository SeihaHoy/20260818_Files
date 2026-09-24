# Orchestration framework

A minimal, dependency-tracked pipeline runner: register Python functions as
"assets" with `@asset(deps=[...])`, and the framework figures out execution
order, runs them, and persists every run to SQL Server for audit and
monitoring.

## Layout

```
framework/
    core.py       Asset class, @asset decorator, dependency resolver
    db.py         All SQL Server reads/writes (orch.* tables)
    executor.py   Orchestrator — runs assets in order, logs to SQL
    lineage.py    Draws the dependency graph, colored by run status
sample_project/
    config.py     Connection strings (fill these in)
    pipeline.py   5 sample assets: extract (Oracle + parquet) -> clean -> report -> PBI refresh
    run.py        Entry point for Task Scheduler
sql/
    schema.sql    Run once against your target database
```

## Setup

1. `pip install -r requirements.txt`
2. Run `sql/schema.sql` against your SQL Server database once, to create
   the `orch` schema.
3. Fill in `sample_project/config.py` with your real connection strings.
4. Implement `get_pbi_access_token()` in `pipeline.py` with your existing
   Power BI auth flow.
5. Point a Task Scheduler task at `python.exe sample_project\run.py`.

## How it fits together

- `pipeline.py` defines assets with `@asset(deps=[...])`. Importing the
  module registers them — it does not run anything.
- `run.py` builds an `Orchestrator`, then calls `materialize_all()`, which:
  1. Resolves execution order from the dependency graph (`core.py`)
  2. Syncs asset/dependency definitions into SQL (`db.sync_assets`)
  3. Runs each asset in order, logging start/end/status/error per asset
     to `orch.asset_run`
  4. Marks any assets downstream of a failure as `skipped` rather than
     running them against incomplete upstream data
- `lineage.draw_lineage()` reads the latest status per asset back out of
  SQL and renders the dependency graph as a PNG — green for success, red
  for failed, gray for skipped/pending. This is the crucial-data-in-SQL,
  visual-in-Python split: the audit trail lives in the database and
  survives independent of any one lineage image; the image is just a
  read-only rendering of it, regenerated on demand.

## Adding a new pipeline

Create a new module next to `pipeline.py` with its own `@asset` functions
and its own `Orchestrator(conn_str, pipeline_name=...)` — asset names are
scoped per pipeline in SQL (`uq_asset_name_per_pipeline`), so two
pipelines can both have an asset called `extract_data` without colliding.

## Testing without live sources

Each asset function is a plain Python function — call it directly to
test in isolation, e.g. `pipeline.clean_and_transform.func()` after
manually setting `.result` on its dependencies. No framework machinery
required for unit-level testing.
