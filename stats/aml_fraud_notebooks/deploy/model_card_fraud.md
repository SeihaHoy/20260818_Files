# Model card - fraud_champion_logit
*Generated 2026-09-19 from notebooks 06 and 08.*

**Purpose.** Score card-not-present transactions for fraud; RED/AMBER/GREEN policy in `deploy/policy.json`.
**Model.** Logistic regression on 9 features (log_amt, hour, night, foreign, new_device, amt_z, log_hrs_since_prev, n_prev_1h, n_prev_24h); interpretable reason codes.
**Training data.** 59,029 card-online transactions up to day 255 (243 confirmed frauds). Labels: chargebacks (delayed by weeks).
**Out-of-time performance (95% cluster-bootstrap intervals).** AUC 0.946 [0.921, 0.968];
average precision 0.711 [0.600, 0.789]; recall@1% 0.721 [0.641, 0.802].
**Latency.** 0.9 ms per single-row score (model only).
**Known limitations.** Trained on confirmed fraud only (unlabelled fraud counts as genuine); performance drops when fraudsters evade the main tells (see monitoring section); synthetic lab data - re-validate on bank data.
**Monitoring.** Monthly: score PSI, feature PSI, AP bootstrap traffic light vs reference, binomial calibration by band. Trigger table: see `monitoring_decision`.
**Governance.** Owner: ______  Validator: ______  Approval date: ______  Next review: 6 months or on RED.
