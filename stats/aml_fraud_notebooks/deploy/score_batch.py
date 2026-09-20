#!/usr/bin/env python
"""
Batch scoring job for card-not-present fraud  (deployment artefact, see notebook 08)

Usage
-----
python deploy/score_batch.py --batch batch.csv.gz --history history.csv.gz --out scored.csv [--model models/fraud_champion.joblib] [--policy deploy/policy.json]

* batch / history : raw transaction extracts (same columns as data/raw/transactions.csv.gz)
* history gives the customer context needed for velocity / behavioural features (only PAST rows are used)
* output          : one row per card-online transaction in the batch with score, traffic light, reason codes
Exit code != 0 on data-contract violations, so a scheduler (cron / Airflow / SQL Agent) can alert.
"""
import argparse, json, sys, time
from pathlib import Path
import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import amlkit as ak

REQUIRED = ["txn_id", "customer_id", "ts", "channel", "amount", "currency", "country", "new_device"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", required=True); ap.add_argument("--history", default=None); ap.add_argument("--out", required=True)
    ap.add_argument("--model", default=str(ROOT / "models" / "fraud_champion.joblib"))
    ap.add_argument("--policy", default=str(ROOT / "deploy" / "policy.json"))
    a = ap.parse_args()
    t0 = time.time()

    batch = pd.read_csv(a.batch, parse_dates=["ts"])
    missing = [c for c in REQUIRED if c not in batch.columns]
    if missing:
        sys.exit(f"DATA CONTRACT VIOLATION: missing columns {missing}")
    hist = pd.read_csv(a.history, parse_dates=["ts"]) if a.history else batch.iloc[0:0]
    allrows = pd.concat([hist, batch], ignore_index=True)

    clean = ak.clean_transactions(allrows)
    cards = clean[clean.channel == "card_online"]
    feats = ak.card_features(cards)
    new_ids = set(batch.txn_id)
    X = feats[feats.txn_id.isin(new_ids)].copy()

    bundle = joblib.load(a.model); policy = json.load(open(a.policy))
    model, cols = bundle["model"], bundle["features"]
    X["score"] = model.predict_proba(X[cols])[:, 1]
    X["light"] = np.where(X.score >= policy["red"], "RED", np.where(X.score >= policy["amber"], "AMBER", "GREEN"))
    X["reasons"] = ak.reason_codes(model, cols, X)
    out = X[["txn_id", "customer_id", "ts", "amount_usd", "score", "light", "reasons"]].sort_values("score", ascending=False)
    out.to_csv(a.out, index=False)
    print(json.dumps(dict(model=bundle["name"], scored=len(out), red=int((out.light == "RED").sum()), amber=int((out.light == "AMBER").sum()),
                          seconds=round(time.time() - t0, 2))))


if __name__ == "__main__":
    main()
