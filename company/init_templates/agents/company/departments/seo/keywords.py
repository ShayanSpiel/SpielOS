"""Evidence-first keyword opportunity mapping; never invents demand volume."""

import re


def build_opportunities(seed_topics, search_rows=()):
    rows = list(search_rows)
    values = []
    for seed in seed_topics:
        normalized = re.sub(r"\s+", " ", seed.strip().lower())
        matches = [row for row in rows if normalized in str((row.get("keys") or [""])[0]).lower()]
        impressions = sum(float(row.get("impressions", 0)) for row in matches)
        clicks = sum(float(row.get("clicks", 0)) for row in matches)
        values.append({"keyword": normalized,
                       "demand_status": "measured" if matches else "unknown",
                       "impressions": impressions if matches else None,
                       "clicks": clicks if matches else None,
                       "evidence_rows": len(matches)})
    return values
