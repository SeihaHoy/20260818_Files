"""
Sample pipeline: Oracle + parquet -> clean/transform -> report -> Power BI refresh.

Importing this module registers all five assets with the framework —
run.py just needs `import pipeline` before calling materialize_all().
"""

import oracledb
import pandas as pd
import pyodbc
import requests

import config
from framework import asset


@asset(group="extract", owner="august@company.com",
       description="Pulls transactions from Oracle transactions_view")
def extract_oracle_data():
    with oracledb.connect(config.ORACLE_DSN) as conn:
        return pd.read_sql("SELECT * FROM transactions_view", conn)


@asset(group="extract", owner="august@company.com",
       description="Reads incoming parquet files")
def extract_parquet_data():
    return pd.read_parquet(config.PARQUET_DIR)


@asset(deps=[extract_oracle_data, extract_parquet_data], group="transform",
       owner="august@company.com", description="Dedupes, drops nulls, casts types")
def clean_and_transform():
    oracle_df = extract_oracle_data.result
    parquet_df = extract_parquet_data.result

    combined = pd.concat([oracle_df, parquet_df], ignore_index=True)
    combined = combined.drop_duplicates(subset=["transaction_id"])
    combined = combined.dropna(subset=["account_id", "amount"])
    combined["amount"] = combined["amount"].astype(float)
    return combined


@asset(deps=[clean_and_transform], group="load", owner="august@company.com",
       description="Aggregates and writes to rpt.daily_account_summary")
def build_report():
    df = clean_and_transform.result
    report = (
        df.groupby(["account_id", "transaction_date"])
          .agg(total_amount=("amount", "sum"), txn_count=("transaction_id", "count"))
          .reset_index()
    )

    with pyodbc.connect(config.SQL_CONN_STR) as conn:
        cursor = conn.cursor()
        cursor.execute("TRUNCATE TABLE rpt.daily_account_summary")
        cursor.executemany(
            "INSERT INTO rpt.daily_account_summary (account_id, txn_date, total_amount, txn_count) "
            "VALUES (?, ?, ?, ?)",
            report.values.tolist()
        )
        conn.commit()
    return report


@asset(deps=[build_report], group="publish", owner="august@company.com",
       description="Triggers Power BI dataset refresh")
def refresh_power_bi():
    token = get_pbi_access_token()
    requests.post(
        f"https://api.powerbi.com/v1.0/myorg/groups/{config.PBI_GROUP_ID}"
        f"/datasets/{config.PBI_DATASET_ID}/refreshes",
        headers={"Authorization": f"Bearer {token}"}
    )


def get_pbi_access_token():
    """Replace with your existing MSAL / service-principal auth helper."""
    raise NotImplementedError("Wire up your Power BI auth flow here")
