"""
amlkit.py  -  shared helpers for the Fraud & AML statistics notebooks
=====================================================================
Framework   : Fraud Analytics (Baesens et al.)  - process model + descriptive/predictive/SNA
Concepts    : AML Transaction Monitoring Systems Implementation (Chau & van Dijck Nemcsik)
Stat. guide : Practical Statistics for Data Scientists (Bruce, Bruce, Gedeck)

Everything here is deterministic (fixed seeds) so results are reproducible.
Swap the synthetic extracts in data/raw/ for your own bank extracts and the
notebooks keep working as long as the column names below are respected.
"""
from pathlib import Path
import numpy as np
import pandas as pd

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
RAW = DATA / "raw"
PROC = DATA / "processed"

START = pd.Timestamp("2025-01-01")
DAYS = 365
KHR_PER_USD = 4100
CTR_THRESHOLD = 10_000          # cash reporting threshold used in the examples (USD)

CHANNELS = ["cash_deposit", "cash_withdrawal", "wire_in", "wire_out",
            "transfer_in", "transfer_out", "card_pos", "card_online"]
CREDITS = ["cash_deposit", "wire_in", "transfer_in"]
DEBITS = ["cash_withdrawal", "wire_out", "transfer_out", "card_pos", "card_online"]
HIGH_RISK = ["HR_A", "HR_B", "HR_C"]          # placeholders for FATF-style high-risk jurisdictions
FOREIGN_LOW = ["TH", "VN", "SG", "US", "CN", "HK"]

SEGMENTS = ["retail_salaried", "retail_self_employed", "small_business",
            "cash_intensive", "corporate"]
_SEG_SHARE = [0.55, 0.20, 0.13, 0.07, 0.05]
_SEG_TXN_PM = [10, 14, 30, 45, 60]              # transactions per month (mean)
_SEG_SHIFT = [0.0, 0.3, 0.8, 1.0, 1.6]          # log-amount shift
_SEG_LAUNDER_W = [0.4, 1.2, 2.0, 3.0, 1.5]      # relative propensity to be a launderer
_CH_PROBS = {
    "retail_salaried":      [0.04, 0.08, 0.01, 0.01, 0.20, 0.20, 0.36, 0.10],
    "retail_self_employed": [0.10, 0.10, 0.02, 0.02, 0.18, 0.18, 0.28, 0.12],
    "small_business":       [0.16, 0.10, 0.06, 0.06, 0.16, 0.16, 0.20, 0.10],
    "cash_intensive":       [0.30, 0.14, 0.02, 0.03, 0.10, 0.12, 0.19, 0.10],
    "corporate":            [0.03, 0.03, 0.22, 0.22, 0.15, 0.15, 0.10, 0.10],
}
_CH_MU = dict(zip(CHANNELS, [6.3, 5.8, 7.6, 7.5, 6.2, 6.1, 3.7, 4.0]))
_CH_SD = dict(zip(CHANNELS, [0.9, 0.8, 1.0, 1.0, 0.9, 0.9, 0.8, 0.9]))
TYPOLOGIES = ["structuring", "smurfing_low", "pass_through", "mule_ring", "commingling"]


# --------------------------------------------------------------------------
# 1. Synthetic data generator  (stands in for your core-banking extracts)
# --------------------------------------------------------------------------
def make_dataset(n_customers=3500, seed=42, launder_share=0.035):
    """
    Returns dict(customers, transactions, truth).
      customers    : KYC table (dirty on purpose: missing values, duplicates, label typos)
      transactions : raw transaction extract (dirty on purpose: duplicates, KHR, non-positive)
      truth        : HIDDEN ground truth (is_launderer, typology, ring_id).  In real life this
                     does not exist - it is here so you can measure how good your methods are.
    """
    rng = np.random.default_rng(seed)
    n = n_customers
    seg_idx = rng.choice(len(SEGMENTS), size=n, p=_SEG_SHARE)
    seg = np.array(SEGMENTS)[seg_idx]
    cust_off = rng.normal(0, 0.4, n)                       # personal log-scale amount offset
    rate = np.array(_SEG_TXN_PM)[seg_idx] * rng.lognormal(0, 0.35, n)

    # ---- baseline transactions (vectorised) -------------------------------
    counts = rng.poisson(rate * 12)
    cid = np.repeat(np.arange(n), counts)
    m = len(cid)
    ch = np.empty(m, dtype=object)
    for s_i, s in enumerate(SEGMENTS):
        mask = seg_idx[cid] == s_i
        ch[mask] = rng.choice(CHANNELS, size=mask.sum(), p=_CH_PROBS[s])
    ch_idx = pd.Series(ch).map({c: i for i, c in enumerate(CHANNELS)}).values
    card = np.isin(ch, ["card_pos", "card_online"])
    mu = np.array([_CH_MU[c] for c in CHANNELS])[ch_idx] \
        + np.array(_SEG_SHIFT)[seg_idx[cid]] * np.where(card, 0.5, 1.0) + cust_off[cid]
    sd = np.array([_CH_SD[c] for c in CHANNELS])[ch_idx]
    amount = np.clip(rng.lognormal(mu, sd), 1, 5_000_000).round(2)
    day = rng.integers(0, DAYS, m)
    hour = np.clip(rng.normal(13, 4.5, m), 0, 23.99)
    online = ch == "card_online"
    o_idx = np.flatnonzero(online)
    pick = o_idx[rng.random(len(o_idx)) < 0.4]
    hour[pick] = rng.uniform(0, 24, len(pick))

    country = np.full(m, "KH", dtype=object)
    wire = np.isin(ch, ["wire_in", "wire_out"])
    country[wire] = rng.choice(["KH"] + FOREIGN_LOW + HIGH_RISK, size=wire.sum(),
                               p=[0.10] + [0.13] * 6 + [0.04] * 3)
    country[online] = rng.choice(["KH"] + FOREIGN_LOW, size=online.sum(), p=[0.80] + [0.20 / 6] * 6)

    cp = np.full(m, -1, dtype=np.int64)
    tr = np.isin(ch, ["transfer_in", "transfer_out"])
    # (legacy draws kept so the main random stream - and every other table - is unchanged)
    _ = rng.integers(0, 20, m); _ = rng.random(m); _ = rng.integers(0, n, m); _ = rng.integers(0, 5000, m); _ = rng.integers(0, 5000, wire.sum())
    # --- counterparties: most payments go to a small, recurring payee list (sparse, realistic network) ---
    rp = np.random.default_rng(seed + 7)
    block = (np.arange(n) // 10) * 10
    payees = np.column_stack([np.minimum(n - 1, block + rp.integers(0, 10, n)), np.minimum(n - 1, block + rp.integers(0, 10, n)),
                              rp.integers(0, n, n), rp.integers(0, n, n)])                   # 2 'household/business group' + 2 random payees
    ext_partners = n + rp.integers(0, 5000, (n, 3))                                          # 3 recurring external partners for wires
    pick = rp.integers(0, 4, m); habit = rp.random(m) < 0.92
    oneoff = np.where(rp.random(m) < 0.7, rp.integers(0, n, m), n + rp.integers(0, 5000, m))
    cp_tr = np.where(habit, payees[cid, pick], oneoff)
    cp[tr] = cp_tr[tr]
    cp_w = np.where(rp.random(m) < 0.85, ext_partners[cid, rp.integers(0, 3, m)], n + rp.integers(0, 5000, m))
    cp[wire] = cp_w[wire]
    new_dev = np.zeros(m, dtype=int)
    new_dev[online] = (rng.random(online.sum()) < 0.04).astype(int)
    is_fraud = np.zeros(m, dtype=int)

    base = pd.DataFrame(dict(customer_id=cid, day=day, hour=hour, channel=ch, amount=amount,
                             counterparty_id=cp, country=country, is_fraud=is_fraud, new_device=new_dev))

    # ---- KYC baseline monthly credits (used to build a realistic declared turnover) --
    cr = base[base.channel.isin(CREDITS)].groupby("customer_id").amount.sum().reindex(range(n)).fillna(0) / 12
    cd_rate_day = (base[base.channel == "cash_deposit"].groupby("customer_id").size()
                   .reindex(range(n)).fillna(0) / DAYS).values

    # ---- launderers ---------------------------------------------------------
    n_l = int(round(launder_share * n))
    w = np.array(_SEG_LAUNDER_W)[seg_idx]
    launderers = rng.choice(n, size=n_l, p=w / w.sum(), replace=False)
    typ_p = [0.25, 0.15, 0.20, 0.22, 0.18]
    typ = rng.choice(TYPOLOGIES, size=n_l, p=typ_p)
    for i, c in enumerate(launderers):                        # commingling only makes sense for businesses
        if typ[i] == "commingling" and seg[c] not in ("small_business", "cash_intensive", "retail_self_employed"):
            typ[i] = "structuring"
    truth = pd.DataFrame(dict(customer_id=np.arange(n), is_launderer=0, typology="none", ring_id=-1))
    truth.loc[launderers, "is_launderer"] = 1
    truth.loc[launderers, "typology"] = typ

    rows = []
    def add(c, d, h, chn, amt, cpid=-1, ctry="KH"):
        rows.append((c, int(d), float(h), chn, round(float(amt), 2), int(cpid), ctry, 0, 0))

    shells = n + 5000 + np.arange(6)                           # small pool of shared shell counterparties
    for c, t in zip(launderers, typ):
        if t == "structuring":
            for _ in range(rng.integers(4, 10)):
                d0 = rng.integers(0, DAYS - 6)
                for _ in range(rng.integers(3, 7)):
                    add(c, d0 + rng.integers(0, 5), rng.uniform(9, 17), "cash_deposit", rng.uniform(7500, 9900))
        elif t == "smurfing_low":                              # 'low and slow' - below the single-txn floor of the rule
            for _ in range(rng.integers(5, 10)):
                d0 = rng.integers(0, DAYS - 6)
                for _ in range(rng.integers(5, 10)):
                    add(c, d0 + rng.integers(0, 5), rng.uniform(9, 17), "cash_deposit", rng.uniform(1800, 2450))
        elif t == "pass_through":
            for _ in range(rng.integers(4, 9)):
                d0 = rng.integers(0, DAYS - 4)
                a = rng.lognormal(10.6, 0.5)
                add(c, d0, rng.uniform(9, 15), "wire_in", a, n + rng.integers(0, 5000),
                    rng.choice(FOREIGN_LOW + HIGH_RISK))
                add(c, d0 + rng.integers(1, 3), rng.uniform(9, 16), "wire_out", a * rng.uniform(0.90, 0.98),
                    rng.choice(shells), rng.choice(HIGH_RISK))
        elif t == "commingling":
            start = rng.integers(90, 240)
            mu_c = _CH_MU["cash_deposit"] + _SEG_SHIFT[seg_idx[c]] + cust_off[c]
            for d in range(start, DAYS):
                for _ in range(rng.poisson(2.0 * cd_rate_day[c] + 0.05)):
                    add(c, d, np.clip(rng.normal(13, 4), 0, 23.9), "cash_deposit", rng.lognormal(mu_c, 0.9))

    # mule rings: groups of 6-9 members with dense internal transfers, then cash-out
    mules = launderers[typ == "mule_ring"]
    ring_id, pos = 0, 0
    while pos < len(mules):
        size = int(rng.integers(6, 10))
        members = mules[pos:pos + size]
        pos += size
        if len(members) < 3:
            members = mules[max(0, len(mules) - 6):]
        truth.loc[members, "ring_id"] = ring_id
        for _ in range(rng.integers(35, 55)):
            a, b = rng.choice(members, 2, replace=False)
            d = rng.integers(0, DAYS - 2)
            amt = rng.uniform(800, 3000)
            h = rng.uniform(8, 20)
            add(a, d, h, "transfer_out", amt, b)
            add(b, d, h + 0.05, "transfer_in", amt, a)
            if rng.random() < 0.5:
                add(b, d + rng.integers(0, 2), rng.uniform(9, 17), "cash_withdrawal", amt * rng.uniform(0.9, 1.0))
        for mbr in members:                                    # 'victim' payments into the ring
            for _ in range(rng.integers(6, 14)):
                v = rng.integers(0, n)
                d = rng.integers(0, DAYS)
                amt = rng.uniform(300, 2500)
                add(v, d, rng.uniform(8, 20), "transfer_out", amt, mbr)
                add(mbr, d, rng.uniform(8, 20), "transfer_in", amt, v)
        ring_id += 1

    inj = pd.DataFrame(rows, columns=base.columns)

    # ---- payment (card-not-present) fraud bursts --------------------------------------
    frows = []
    victims = rng.choice(n, size=int(0.015 * n), replace=False)
    for c in victims:
        for _ in range(rng.integers(1, 4)):
            d0 = rng.integers(0, DAYS)
            burst = rng.random() < 0.4                          # 40% fast bursts, 60% low-and-slow (harder to see)
            k = rng.integers(3, 9) if burst else rng.integers(1, 4)
            h0 = rng.choice([22.0, 23.0, 0.0, 1.0, 2.0, 3.0, 4.0]) if rng.random() < 0.5 else rng.uniform(6, 21)
            for j in range(k):
                gap = rng.uniform(0.02, 0.15) if burst else rng.uniform(1, 6)
                frows.append((c, d0, h0 + j * gap, "card_online", round(float(rng.lognormal(4.9, 0.9)), 2), -1,
                              rng.choice(["KH"] + FOREIGN_LOW, p=[0.35] + [0.65 / 6] * 6), 1, int(rng.random() < 0.55)))
    fr = pd.DataFrame(frows, columns=base.columns)
    fr["hour"] = fr["hour"] % 24

    txn = pd.concat([base, inj, fr], ignore_index=True)
    txn = txn.sort_values(["day", "hour"]).reset_index(drop=True)
    txn.insert(0, "txn_id", np.arange(1, len(txn) + 1))
    txn["ts"] = START + pd.to_timedelta(txn["day"], unit="D") + pd.to_timedelta(txn["hour"], unit="h")
    txn["ts"] = txn["ts"].dt.floor("s")
    txn["currency"] = "USD"

    # ---- make the extract dirty (on purpose) ------------------------------------
    khr = txn.channel.isin(["card_pos", "transfer_in", "transfer_out", "cash_withdrawal"]) & (rng.random(len(txn)) < 0.08)
    txn.loc[khr, "currency"] = "KHR"
    txn.loc[khr, "amount"] = (txn.loc[khr, "amount"] * KHR_PER_USD / 100).round() * 100
    bad = rng.random(len(txn)) < 0.0006
    txn.loc[bad, "amount"] = np.where(rng.random(bad.sum()) < 0.5, 0.0, -txn.loc[bad, "amount"])
    dup = txn.sample(frac=0.002, random_state=seed)
    txn = pd.concat([txn, dup], ignore_index=True).sample(frac=1, random_state=seed).sort_values("ts").reset_index(drop=True)
    txn = txn[["txn_id", "customer_id", "ts", "channel", "amount", "currency", "counterparty_id",
               "country", "new_device", "is_fraud"]]

    # ---- KYC table ------------------------------------------------------------------
    declared = (cr.values * rng.lognormal(0, 0.5, n)).round(-1) + 200
    cust = pd.DataFrame(dict(
        customer_id=np.arange(n),
        segment=seg,
        region=rng.choice(["Phnom Penh", "Siem Reap", "Battambang", "Sihanoukville", "Kampot"], n,
                          p=[0.45, 0.2, 0.12, 0.13, 0.10]),
        tenure_years=np.clip(rng.gamma(2, 2.5, n), 0.1, 25).round(1),
        declared_monthly_turnover=declared,
        country_risk=rng.choice(["low", "medium", "high"], n, p=[0.85, 0.12, 0.03]),
        is_pep=(rng.random(n) < 0.01).astype(int),
        community_id=np.arange(n) // 10,
    ))
    cust.loc[rng.random(n) < 0.04, "tenure_years"] = np.nan
    cust.loc[rng.random(n) < 0.06, "declared_monthly_turnover"] = np.nan
    messy = rng.random(n) < 0.05
    cust.loc[messy, "segment"] = cust.loc[messy, "segment"].str.replace("_", " ").str.title()
    cust = pd.concat([cust, cust.sample(15, random_state=seed)], ignore_index=True)      # duplicate KYC rows
    return dict(customers=cust, transactions=txn, truth=truth)


def ensure_data(force=False, **kw):
    """Create data/raw/*.csv.gz if they do not exist (idempotent)."""
    RAW.mkdir(parents=True, exist_ok=True)
    PROC.mkdir(parents=True, exist_ok=True)
    f = RAW / "transactions.csv.gz"
    if force or not f.exists():
        d = make_dataset(**kw)
        d["transactions"].to_csv(RAW / "transactions.csv.gz", index=False)
        d["customers"].to_csv(RAW / "customers_kyc.csv", index=False)
        d["truth"].to_csv(DATA / "_hidden_ground_truth.csv", index=False)
    return RAW


def load_raw():
    """Load the raw extracts exactly as your ETL would hand them over."""
    ensure_data()
    txn = pd.read_csv(RAW / "transactions.csv.gz", parse_dates=["ts"])
    kyc = pd.read_csv(RAW / "customers_kyc.csv")
    return txn, kyc


def load_truth():
    """Hidden ground truth - ONLY for evaluating methods in this synthetic lab."""
    ensure_data()
    return pd.read_csv(DATA / "_hidden_ground_truth.csv")


# --------------------------------------------------------------------------
# 2. Cleaning  (Fraud Analytics process model: 'Clean the data')
# --------------------------------------------------------------------------
def clean_transactions(raw):
    t = raw.drop_duplicates(subset="txn_id").copy()
    t["amount_usd"] = np.where(t["currency"] == "KHR", t["amount"] / KHR_PER_USD, t["amount"])
    t = t[t["amount_usd"] > 0].copy()
    t["ts"] = pd.to_datetime(t["ts"])
    t["date"] = t["ts"].dt.normalize()
    t["day"] = (t["date"] - START).dt.days
    t["hour"] = t["ts"].dt.hour
    return t.reset_index(drop=True)


def clean_kyc(kyc):
    k = kyc.copy()
    k["segment"] = k["segment"].str.strip().str.lower().str.replace(" ", "_")
    k = k.drop_duplicates(subset="customer_id").reset_index(drop=True)
    return k


# --------------------------------------------------------------------------
# 3. AML scenario engine  (Chapter 9 running example)
#    "over the past L days, at least N cash deposits, each >= m, aggregate >= A"
# --------------------------------------------------------------------------
def cash_window_matrices(txn, n_customers, min_single=0.0, lookback=5, days=DAYS):
    """Rolling-window count and amount of cash deposits (>= min_single) per customer x day."""
    cd = txn[(txn["channel"] == "cash_deposit") & (txn["amount_usd"] >= min_single)]
    cnt = np.zeros((n_customers, days))
    amt = np.zeros((n_customers, days))
    np.add.at(cnt, (cd["customer_id"].values, cd["day"].values), 1)
    np.add.at(amt, (cd["customer_id"].values, cd["day"].values), cd["amount_usd"].values)
    ccnt, camt = cnt.cumsum(axis=1), amt.cumsum(axis=1)
    wc, wa = ccnt.copy(), camt.copy()
    wc[:, lookback:] = ccnt[:, lookback:] - ccnt[:, :-lookback]
    wa[:, lookback:] = camt[:, lookback:] - camt[:, :-lookback]
    return wc, wa


def run_scenario(txn, n_customers, min_single=2500, min_count=3, min_agg=10_000,
                 lookback=5, cooldown=30):
    """Return one row per alert (first trigger, then suppression for `cooldown` days)."""
    wc, wa = cash_window_matrices(txn, n_customers, min_single, lookback)
    trig = (wc >= min_count) & (wa >= min_agg)
    out = []
    for c in np.flatnonzero(trig.any(axis=1)):
        last = -10**6
        for d in np.flatnonzero(trig[c]):
            if d - last >= cooldown:
                out.append((c, d, wa[c, d], wc[c, d]))
                last = d
    a = pd.DataFrame(out, columns=["customer_id", "alert_day", "agg_amt", "n_trx"])
    a.insert(0, "alert_id", np.arange(1, len(a) + 1))
    a["alert_date"] = START + pd.to_timedelta(a["alert_day"], unit="D")
    return a


def _hash_uniform(a, b, salt):
    """Deterministic U(0,1) per (a, b, salt): the same alert always gets the same 'investigator outcome'."""
    with np.errstate(over="ignore"):
        x = (np.asarray(a).astype(np.uint64) * np.uint64(0x9E3779B97F4A7C15)) \
            ^ (np.asarray(b).astype(np.uint64) * np.uint64(0xC2B2AE3D27D4EB4F)) \
            ^ np.uint64(salt * 0x165667B19E3779F9 % (1 << 63))
        x ^= x >> np.uint64(33)
        x *= np.uint64(0xFF51AFD7ED558CCD)
        x ^= x >> np.uint64(33)
        x *= np.uint64(0xC4CEB9FE1A85EC53)
        x ^= x >> np.uint64(33)
    return (x >> np.uint64(11)).astype(np.float64) / float(1 << 53)


def simulate_dispositions(alerts, truth, seed=7):
    """
    Simulate the investigation funnel (Chapter 9: FPR I / FPR II / TPR I / TPR II).
      L1 triage  -> closed as false positive (FPR I)
      L2 invest. -> closed after investigation (FPR II)  or  STR filed (TPR II)
    Investigators are imperfect: some launderers are missed, some innocents get an STR (defensive filing).
    Outcomes are a deterministic function of (customer, alert_day) so that what-if runs are comparable.
    """
    a = alerts.merge(truth[["customer_id", "is_launderer"]], on="customer_id", how="left")
    u1 = _hash_uniform(a["customer_id"], a["alert_day"], seed * 2 + 1)
    u2 = _hash_uniform(a["customer_id"], a["alert_day"], seed * 2 + 2)
    p_l2 = np.where(a["is_launderer"] == 1, 0.95, 0.35)
    p_str = np.where(a["is_launderer"] == 1, 0.85, 0.03)
    to_l2 = u1 < p_l2
    filed = to_l2 & (u2 < p_str)
    a["investigated"] = to_l2.astype(int)
    a["str_filed"] = filed.astype(int)                       # <- the "productive alert" label you would really have
    a["stage"] = np.select([~to_l2, to_l2 & ~filed], ["closed_L1", "closed_L2"], "STR_filed")
    return a.drop(columns=["is_launderer"])


# --------------------------------------------------------------------------
# 4. Feature engineering  (customer level)
# --------------------------------------------------------------------------
def build_customer_features(txn, kyc):
    n = kyc["customer_id"].max() + 1
    g = txn.groupby("customer_id")
    f = pd.DataFrame(index=range(n))
    f["n_txn"] = g.size()
    f["total_amt"] = g["amount_usd"].sum()
    f["mean_amt"] = g["amount_usd"].mean()
    f["median_amt"] = g["amount_usd"].median()
    f["std_amt"] = g["amount_usd"].std()
    f["max_amt"] = g["amount_usd"].max()
    by = txn.pivot_table(index="customer_id", columns="channel", values="amount_usd", aggfunc="sum", fill_value=0)
    for c in CHANNELS:
        f[f"amt_{c}"] = by.get(c)
    f["credits"] = f[[f"amt_{c}" for c in CREDITS]].sum(axis=1)
    f["debits"] = f[[f"amt_{c}" for c in DEBITS]].sum(axis=1)
    f["cash_share_credits"] = f["amt_cash_deposit"] / f["credits"].replace(0, np.nan)
    cd = txn[txn["channel"] == "cash_deposit"]
    f["n_cash_dep"] = cd.groupby("customer_id").size()
    f["near_ctr_cnt"] = cd[(cd.amount_usd >= 0.75 * CTR_THRESHOLD) & (cd.amount_usd < CTR_THRESHOLD)] \
        .groupby("customer_id").size()
    f["sub_floor_cnt"] = cd[(cd.amount_usd >= 1800) & (cd.amount_usd < 2500)].groupby("customer_id").size()
    hr = txn[txn["country"].isin(HIGH_RISK)]
    f["hr_amt"] = hr.groupby("customer_id")["amount_usd"].sum()
    f["hr_share"] = f["hr_amt"] / f["total_amt"]
    f["night_share"] = txn.assign(night=txn.hour.isin([0, 1, 2, 3, 4, 5])).groupby("customer_id")["night"].mean()
    m = txn.assign(month=txn.ts.dt.month, cr=txn.amount_usd.where(txn.channel.isin(CREDITS), 0),
                   db=txn.amount_usd.where(txn.channel.isin(DEBITS), 0)).groupby(["customer_id", "month"])[["cr", "db"]].sum()
    m["flow"] = np.minimum(m.cr, m.db) / np.maximum(np.maximum(m.cr, m.db), 1)
    m.loc[m.cr < 20_000, "flow"] = 0
    f["flowthrough_max"] = m.groupby("customer_id")["flow"].max()
    f["n_counterparties"] = txn[txn.counterparty_id >= 0].groupby("customer_id")["counterparty_id"].nunique()
    _, wa = cash_window_matrices(txn, n, 0.0, 5)
    f["max_cash_agg_5d"] = wa.max(axis=1)
    f = f.fillna({c: 0 for c in f.columns if c not in ("cash_share_credits", "std_amt")})
    f["cash_share_credits"] = f["cash_share_credits"].fillna(0)
    f["std_amt"] = f["std_amt"].fillna(0)
    f = f.reset_index(names="customer_id").merge(kyc, on="customer_id", how="left")
    f["monthly_credits"] = f["credits"] / 12
    f["turnover_ratio"] = f["monthly_credits"] / f["declared_monthly_turnover"]
    return f


# --------------------------------------------------------------------------
# 5. Statistics helpers used across notebooks
# --------------------------------------------------------------------------
def psi(expected, actual, bins=10, eps=1e-6):
    """Population / System Stability Index (Fraud Analytics ch.6: SSI = sum (o-e) ln(o/e))."""
    expected, actual = np.asarray(expected, float), np.asarray(actual, float)
    edges = np.unique(np.quantile(expected, np.linspace(0, 1, bins + 1)))
    edges[0], edges[-1] = -np.inf, np.inf
    e = np.histogram(expected, edges)[0] / len(expected) + eps
    a = np.histogram(actual, edges)[0] / len(actual) + eps
    return float(np.sum((a - e) * np.log(a / e)))


def ks_gain(y, score):
    from scipy.stats import ks_2samp
    y, score = np.asarray(y), np.asarray(score)
    return ks_2samp(score[y == 1], score[y == 0]).statistic


def lift_table(y, score, n_bins=10):
    d = pd.DataFrame(dict(y=np.asarray(y), s=np.asarray(score)))
    d["decile"] = pd.qcut(d["s"].rank(method="first", ascending=False), n_bins, labels=False) + 1
    t = d.groupby("decile").agg(n=("y", "size"), frauds=("y", "sum"))
    t["rate"] = t["frauds"] / t["n"]
    t["lift"] = t["rate"] / d["y"].mean()
    t["cum_capture"] = t["frauds"].cumsum() / d["y"].sum()
    return t


def wilson_ci(k, n, z=1.96):
    """Wilson score interval for a proportion - works for rare events, unlike the naive normal CI."""
    if n == 0:
        return (np.nan, np.nan)
    p = k / n
    den = 1 + z**2 / n
    c = (p + z**2 / (2 * n)) / den
    h = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / den
    return c - h, c + h


# --------------------------------------------------------------------------
# 6. Deployment helpers (used by notebook 08 and deploy/score_batch.py)
# --------------------------------------------------------------------------
CARD_FEATURES_TXN = ["log_amt", "hour", "night", "foreign", "new_device"]
CARD_FEATURES_BEH = ["amt_z", "log_hrs_since_prev", "n_prev_1h", "n_prev_24h"]
CARD_FEATURES = CARD_FEATURES_TXN + CARD_FEATURES_BEH


def card_features(cards):
    """
    Feature engineering for card-online transactions (identical to notebook 06).
    `cards` needs: customer_id, ts, amount_usd, hour, country, new_device.  Uses only PAST information per customer.
    Training/serving parity: the SAME function must be used offline and in production.
    """
    c = cards.sort_values(["customer_id", "ts"]).reset_index(drop=True).copy()
    c["log_amt"] = np.log(c["amount_usd"])
    g = c.groupby("customer_id")
    k = g.cumcount()
    s1 = g["log_amt"].cumsum() - c["log_amt"]
    s2 = (c["log_amt"] ** 2).groupby(c["customer_id"]).cumsum() - c["log_amt"] ** 2
    mu_prev = s1 / k.replace(0, np.nan)
    var_prev = (s2 / k.replace(0, np.nan) - mu_prev ** 2).clip(lower=0)
    c["amt_z"] = ((c["log_amt"] - mu_prev) / np.sqrt(var_prev + 0.25)).fillna(0)
    c["log_hrs_since_prev"] = np.log1p(g["ts"].diff().dt.total_seconds().div(3600).fillna(999).clip(upper=999))
    tmp = c.set_index("ts")
    for w in ("1h", "24h"):
        c[f"n_prev_{w}"] = tmp.groupby("customer_id")["amount_usd"].rolling(w, closed="left").count().fillna(0).values
    c["night"] = c["hour"].isin([22, 23, 0, 1, 2, 3, 4, 5]).astype(int)
    c["foreign"] = (c["country"] != "KH").astype(int)
    return c


def reason_codes(model_pipe, cols, X, top=3):
    """Top positive contributions (coef x standardised value) of a scaler+logistic pipeline = analyst-facing reason codes."""
    sc, lg = model_pipe[0], model_pipe[-1]
    contrib = sc.transform(X[cols]) * lg.coef_[0]
    order = np.argsort(-contrib, axis=1)[:, :top]
    return [", ".join(cols[j] for j in row if contrib[i, j] > 0) for i, row in enumerate(order)]
