"""Evidence gate for proposing a bounded strategy change."""

from __future__ import annotations


MIN_STRATEGIC_FAILURES = 3


def strategic_frontier(children: list[dict] | tuple[dict, ...]) -> dict | None:
    """Build one bounded business-context experiment proposal when warranted."""

    for child in children or ():
        history = list(child.get("history") or ())[:MIN_STRATEGIC_FAILURES]
        if len(history) < MIN_STRATEGIC_FAILURES:
            continue
        supporting_ids = []
        failed_run_ids = []
        hypothesis_ids = []
        qualified = True
        for item in history:
            run = item.get("run") or {}
            evaluation = item.get("evaluation") or {}
            metrics = evaluation.get("metrics") or {}
            hypothesis = item.get("hypothesis") or {}
            result = metrics.get("hypothesis_result") or {}
            evidence = [row for row in item.get("evidence") or ()
                        if row.get("validity") == "business" and row.get("id")]
            if not (
                run.get("run_type") == "business_experiment"
                and run.get("evidence_validity") == "business"
                and evaluation.get("validity") == "business"
                and not evaluation.get("goal_met")
                and metrics.get("execution_competent") is True
                and metrics.get("system_trustworthy") is True
                and hypothesis.get("status") == "rejected"
                and result.get("hypothesis_id") == run.get("hypothesis_id")
                and result.get("prediction_tested") is True
                and result.get("status") == "rejected"
                and evidence
            ):
                qualified = False
                break
            supporting_ids.extend(row["id"] for row in evidence)
            failed_run_ids.append(run["id"])
            hypothesis_ids.append(hypothesis["id"])
        if not qualified:
            continue
        candidate = (child.get("config") or {}).get("strategic_candidate") or {}
        kind = candidate.get("kind")
        proposal = str(candidate.get("proposal") or "").strip()
        scope = str(candidate.get("scope") or "").strip()
        experiment = candidate.get("experiment") or {}
        contradictions = str(candidate.get("contradictions_assessment") or "").strip()
        try:
            confidence = float(candidate.get("confidence"))
        except (TypeError, ValueError):
            continue
        if (kind not in {"company", "icp", "positioning", "priorities",
                         "constraints", "preferences"} or not proposal or not scope
                or not contradictions or not isinstance(experiment, dict)
                or not all(experiment.get(key) for key in (
                    "hypothesis", "changed_variable", "stop_condition"))
                or not 0.0 <= confidence <= 1.0):
            continue
        return {
            "action": "propose_strategic_experiment",
            "status": "proposed",
            "source_goal_id": child["id"],
            "strategy_category": kind,
            "proposal": proposal,
            "scope": scope,
            "experiment": experiment,
            "confidence": confidence,
            "supporting_evidence_ids": list(dict.fromkeys(supporting_ids)),
            "contradicting_evidence_ids": [],
            "contradictions_assessment": contradictions,
            "failed_run_ids": failed_run_ids,
            "rejected_hypothesis_ids": hypothesis_ids,
            "reasoning": {
                "execution": "competent",
                "system": "trustworthy",
                "persistent_business_failure": True,
                "proposed_category": kind,
            },
            "required_owner_authority": True,
            "strategy_mutated": False,
        }
    return None
