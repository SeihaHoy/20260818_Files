/* ============================================================
   Orchestration Tool — Metadata & Audit Schema (SQL Server)
   Run this once against your target database before first use.
   ============================================================ */

CREATE SCHEMA orch;
GO

CREATE TABLE orch.pipeline (
    pipeline_id     INT IDENTITY(1,1) PRIMARY KEY,
    pipeline_name   VARCHAR(100)    NOT NULL,
    description     VARCHAR(500)    NULL,
    is_active       BIT             NOT NULL DEFAULT (1),
    created_at      DATETIME2(0)    NOT NULL DEFAULT (SYSUTCDATETIME()),
    CONSTRAINT uq_pipeline_name UNIQUE (pipeline_name)
);
GO

CREATE TABLE orch.asset (
    asset_id        INT IDENTITY(1,1) PRIMARY KEY,
    pipeline_id     INT             NOT NULL,
    asset_name      VARCHAR(150)    NOT NULL,
    asset_group     VARCHAR(100)    NULL,
    description     VARCHAR(500)    NULL,
    owner           VARCHAR(200)    NULL,
    created_at      DATETIME2(0)    NOT NULL DEFAULT (SYSUTCDATETIME()),
    CONSTRAINT fk_asset_pipeline FOREIGN KEY (pipeline_id)
        REFERENCES orch.pipeline (pipeline_id),
    CONSTRAINT uq_asset_name_per_pipeline UNIQUE (pipeline_id, asset_name)
);
GO

CREATE TABLE orch.asset_dependency (
    dependency_id       INT IDENTITY(1,1) PRIMARY KEY,
    asset_id            INT NOT NULL,
    depends_on_asset_id INT NOT NULL,
    CONSTRAINT fk_dep_asset FOREIGN KEY (asset_id)
        REFERENCES orch.asset (asset_id),
    CONSTRAINT fk_dep_upstream_asset FOREIGN KEY (depends_on_asset_id)
        REFERENCES orch.asset (asset_id),
    CONSTRAINT uq_dependency_edge UNIQUE (asset_id, depends_on_asset_id),
    CONSTRAINT ck_no_self_dependency CHECK (asset_id <> depends_on_asset_id)
);
GO

CREATE TABLE orch.schedule (
    schedule_id      INT IDENTITY(1,1) PRIMARY KEY,
    pipeline_id      INT             NOT NULL,
    cron_expression  VARCHAR(100)    NOT NULL,
    trigger_source   VARCHAR(50)     NOT NULL DEFAULT ('Task Scheduler'),
    is_enabled       BIT             NOT NULL DEFAULT (1),
    created_at       DATETIME2(0)    NOT NULL DEFAULT (SYSUTCDATETIME()),
    CONSTRAINT fk_schedule_pipeline FOREIGN KEY (pipeline_id)
        REFERENCES orch.pipeline (pipeline_id)
);
GO

CREATE TABLE orch.run (
    run_id          BIGINT IDENTITY(1,1) PRIMARY KEY,
    pipeline_id     INT             NOT NULL,
    triggered_by    VARCHAR(100)    NULL,
    start_time      DATETIME2(0)    NOT NULL DEFAULT (SYSUTCDATETIME()),
    end_time        DATETIME2(0)    NULL,
    status          VARCHAR(20)     NOT NULL DEFAULT ('running'),
    CONSTRAINT fk_run_pipeline FOREIGN KEY (pipeline_id)
        REFERENCES orch.pipeline (pipeline_id),
    CONSTRAINT ck_run_status CHECK (status IN ('running','success','failed','partial'))
);
GO

CREATE TABLE orch.asset_run (
    asset_run_id    BIGINT IDENTITY(1,1) PRIMARY KEY,
    run_id          BIGINT          NOT NULL,
    asset_id        INT             NOT NULL,
    start_time      DATETIME2(0)    NULL,
    end_time        DATETIME2(0)    NULL,
    status          VARCHAR(20)     NOT NULL DEFAULT ('pending'),
    rows_processed  BIGINT          NULL,
    retry_count     INT             NOT NULL DEFAULT (0),
    error_message   VARCHAR(MAX)    NULL,
    CONSTRAINT fk_assetrun_run FOREIGN KEY (run_id)
        REFERENCES orch.run (run_id),
    CONSTRAINT fk_assetrun_asset FOREIGN KEY (asset_id)
        REFERENCES orch.asset (asset_id),
    CONSTRAINT uq_assetrun_per_run UNIQUE (run_id, asset_id),
    CONSTRAINT ck_assetrun_status CHECK (status IN ('pending','running','success','failed','skipped'))
);
GO

CREATE TABLE orch.run_log (
    log_id          BIGINT IDENTITY(1,1) PRIMARY KEY,
    asset_run_id    BIGINT          NOT NULL,
    log_time        DATETIME2(3)    NOT NULL DEFAULT (SYSUTCDATETIME()),
    log_level       VARCHAR(10)     NOT NULL DEFAULT ('INFO'),
    message         VARCHAR(MAX)    NULL,
    CONSTRAINT fk_runlog_assetrun FOREIGN KEY (asset_run_id)
        REFERENCES orch.asset_run (asset_run_id),
    CONSTRAINT ck_runlog_level CHECK (log_level IN ('DEBUG','INFO','WARNING','ERROR'))
);
GO

CREATE INDEX ix_run_pipeline_starttime ON orch.run (pipeline_id, start_time DESC);
CREATE INDEX ix_assetrun_run ON orch.asset_run (run_id);
CREATE INDEX ix_assetrun_asset_status ON orch.asset_run (asset_id, status);
CREATE INDEX ix_dependency_asset ON orch.asset_dependency (asset_id);
CREATE INDEX ix_runlog_assetrun_time ON orch.run_log (asset_run_id, log_time);
GO

CREATE VIEW orch.vw_latest_run_status AS
SELECT
    p.pipeline_name,
    r.run_id,
    r.start_time,
    r.end_time,
    r.status,
    DATEDIFF(SECOND, r.start_time, ISNULL(r.end_time, SYSUTCDATETIME())) AS duration_seconds
FROM orch.run r
JOIN orch.pipeline p ON p.pipeline_id = r.pipeline_id
WHERE r.run_id IN (
    SELECT MAX(run_id) FROM orch.run GROUP BY pipeline_id
);
GO
