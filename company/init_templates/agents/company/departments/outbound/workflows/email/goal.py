#!/usr/bin/env python3
"""Outbound email metric metadata; runtime goals remain company-owned.

The owner edits the goal via data/control.json; the fixed table below only
declares WHICH metrics exist, their kind (floor/ceiling), and the funnel
stage. This mirrors the harness META that drove the v1 loop.
"""

META = {
    "goal": {"name": "reply rate", "metric": "reply_rate", "target": 0.30},
    "supporting_kpis": [
        {"name": "delivered rate", "metric": "delivered_rate", "target": 0.99},
        {"name": "open rate", "metric": "open_rate", "target": 0.80},
        {"name": "click rate", "metric": "click_rate", "target": 0.05},
    ],
    "guardrails": [
        {"name": "bounce rate", "metric": "bounce_rate", "max": 0.02},
        {"name": "spam rate", "metric": "spam_rate", "max": 0.0008},
    ],
}

# Evidence the loop requires before a verdict is trusted
MIN_TRUSTED_SAMPLE = 30
MIN_COMPARE_SAMPLE = 20
MIN_IMPROVEMENT = 0.02  # absolute rate change to call a real movement
MIN_COHORT_SAMPLE = 10
