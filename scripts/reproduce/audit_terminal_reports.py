#!/usr/bin/env python3
"""Offline companion metrics and a conservative, assertion-only SV audit.

Python 3.10+, standard library only. This never changes the benchmark scorer.
Raw archive locations are supplied privately and are not written to outputs.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re

VERSION = "explicit-assertion-v2"
NEGATION = re.compile(r"\b(?:no|not|never|none|neither|without|lack(?:s|ing|ed)?)\b|\b\w+n['’]t\b", re.I)
UNCERTAIN = re.compile(r"\b(?:unclear|unsure|uncertain|unknown|cannot|unable|maybe|may|might|possibly|probably|whether|if|would|could|should|assume|assuming|guess)\b", re.I)
ASSERTION = re.compile(
    r"(?:\b(?:is|are|looks?|appears?|seems?)\s+"
    r"(?:(?:currently|visibly|clearly|fully|completely|now|still|observably|definitely|apparently|observed|seen|confirmed)\s+)*"
    r"(?:to\s+be\s+)?(?:in\s+(?:the\s+)?)?"
    r"|\b(?:observed\s+)?state\s*(?:is\s+|[:=]\s*))"
    r"['\"]?(on|off|open|closed)\b", re.I,
)
BARE_STATE = re.compile(r"\s*['\"]?(on|off|open|closed)['\"]?\s*[.!]?\s*", re.I)
SPATIAL_TAIL = re.compile(r"\s+(?:the|a|an|top|this|that|my|your|its)\b", re.I)


def summary_label(summary, template):
    """Map an explicit present-state assertion, without seeing its expected label.

    Reject the entire summary on negation, uncertainty or a conditional; do not
    infer the complement. Only the queried pair is scored. Spatial on/off,
    historical states, instructions and unrecognized wording stay unmapped.
    Object-reference resolution and complete natural-language semantics are
    outside this deliberately narrow audit.
    """
    if not isinstance(summary, str) or not summary.strip():
        return None, "missing_summary"
    pairs = {"verify_activated_state": {"on", "off"}, "verify_open_state": {"open", "closed"}}
    if template not in pairs:
        raise ValueError(f"unsupported SV template: {template}")
    if NEGATION.search(summary):
        return None, "negation"
    if UNCERTAIN.search(summary):
        return None, "uncertainty_or_conditional"
    labels = set()
    bare = BARE_STATE.fullmatch(summary)
    if bare:
        labels.add(bare.group(1).lower())
    for match in ASSERTION.finditer(summary):
        label = match.group(1).lower()
        if label in {"on", "off"} and SPATIAL_TAIL.match(summary[match.end():]):
            continue
        labels.add(label)
    labels &= pairs[template]
    if len(labels) != 1:
        return None, "conflicting_assertions" if labels else "no_explicit_state_assertion"
    return next(iter(labels)), "mapped"


def dump_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def count_episode(result, meta):
    trace = result["trace"]
    judges = [step["judge_result"] for step in trace]
    assert judges and all(type(j.get("world_success")) is bool for j in judges)
    final = judges[-1]
    world = final["world_success"]
    sv = meta["task_family"].startswith("S4")
    invocation = (trace[-1].get("runtime_action") or {}).get("executed_invocation") or trace[-1].get("invocation") or {}
    report = invocation.get("skill_name") == "report"
    args = invocation.get("arguments") or {}
    assert report == bool(final.get("report_submitted"))
    match = final.get("report_matches_world")
    assert not report or type(match) is bool
    status = args.get("status") if report else "NO_REPORT"
    expected = (final.get("oracle_facts") or {}).get("expected_report_status") if sv else ("success" if world else "fail")
    assert not sv or not report or expected in {"on", "off", "open", "closed", "fail"}
    derived = status == expected if sv else ((status == "success" and world) or (status in {"fail", "unsafe", "invalid"} and not world))
    assert not report or match == derived
    c = Counter(n=1, W=int(world), B=int(bool(world and report and match)), reports=int(report), exact_correct=int(bool(report and match)))
    confusion = ("SV" if sv else "achievement", str(expected), str(status))
    if not sv:
        ever = any(j["world_success"] for j in judges)
        c.update(achievement_n=1, achievement_W=int(world), achievement_ever=int(ever), achievement_lost=int(ever and not world))
        if not report:
            label = "no_report"
        elif status == "success":
            label = "correct_success" if world else "false_success"
        elif status in {"fail", "unsafe", "invalid"}:
            label = "false_failure" if world else "correct_failure"
        else:
            label = "other_invalid_label"
        c["achievement_" + label] += 1
        return c, confusion, None
    dropped = any(not j["world_success"] for j in judges)
    c.update(sv_n=1, sv_W=int(world), sv_B=int(bool(world and report and match)), sv_reports=int(report), sv_exact_correct=int(bool(report and match)), sv_ever_notW=int(dropped), sv_returned_W=int(world and dropped))
    mapped, reason = summary_label(args.get("summary"), meta["functional_template"]) if report else (None, "no_report")
    if not report:
        outcome = "no_report"
    elif expected not in {"on", "off", "open", "closed"}:
        outcome, reason = "unmapped", "unavailable_terminal_state_label"
    elif mapped is None:
        outcome = "unmapped"
    else:
        outcome = "agree" if mapped == expected else "disagree"
    c["sv_summary_" + outcome] += 1
    row = dict(episode_id=result["episode_id"], W=int(world), B=int(bool(world and report and match)), reported_status=status, expected_label=expected or "", summary=args.get("summary") or "", mapped_label=mapped or "", outcome=outcome, reason=reason)
    return c, confusion, row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-map", type=Path, required=True)
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("--exclusions", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    sources = json.loads(args.source_map.read_text())
    meta = {e["episode_id"]: e for e in json.loads(args.pack.read_text())["episodes"]}
    excluded = set(json.loads(args.exclusions.read_text())["episode_ids"])
    assert len(meta) == 1000 and len(excluded) == 10 and excluded <= set(meta)
    assert all(meta[e]["task_family"].startswith("S4") for e in excluded)
    args.out.mkdir(parents=True, exist_ok=True)
    models, audit, confusions, sensitivity = [], [], [], []
    for model, source in sources.items():
        payload = Path(source).read_bytes()
        archive = json.loads(payload)
        results = archive["results"]
        assert len(results) == 1000 and {r["episode_id"] for r in results} == set(meta)
        assert not archive.get("error_count")
        full, retained, confusion = Counter(), Counter(), Counter()
        for result in results:
            eid = result["episode_id"]
            counts, key, row = count_episode(result, meta[eid])
            full.update(counts)
            if eid not in excluded:
                retained.update(counts)
            confusion[key] += 1
            if row is not None:
                audit.append(dict(model=model, **row, excluded_known_setup_issue=int(eid in excluded)))
        assert full["achievement_n"] == retained["achievement_n"] == 875
        assert full["sv_n"] == 125 and retained["sv_n"] == 115 and retained["n"] == 990
        assert sum(full["sv_summary_" + k] for k in ["agree", "disagree", "unmapped", "no_report"]) == 125
        models.append(dict(model=model, archive_sha256=hashlib.sha256(payload).hexdigest(), **dict(full), without_known_sv_issues=dict(retained)))
        for (family, expected, status), count in sorted(confusion.items()):
            confusions.append(dict(model=model, task_group=family, expected=expected, reported=status, count=count))
        fields = ["n", "W", "B", "reports", "exact_correct", "sv_n", "sv_W", "sv_B", "sv_ever_notW", "sv_returned_W", "sv_summary_agree", "sv_summary_disagree", "sv_summary_unmapped", "sv_summary_no_report"]
        sensitivity.append(dict(model=model, **{f"{k}_{scope}": counts[k] for scope, counts in [("full", full), ("retained", retained)] for k in fields}))
        print(model, "A/D/U/M", *(full["sv_summary_" + k] for k in ["agree", "disagree", "unmapped", "no_report"]), flush=True)
    metadata = dict(mapper_version=VERSION, script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), pack_sha256=hashlib.sha256(args.pack.read_bytes()).hexdigest(), exclusions_sha256=hashlib.sha256(args.exclusions.read_bytes()).hexdigest(), models=models)
    (args.out / "archive_metrics.json").write_text(json.dumps(metadata, indent=2) + "\n")
    dump_csv(args.out / "sv_summary_audit.csv", audit)
    dump_csv(args.out / "sv_unmapped_examples.csv", [row for row in audit if row["outcome"] == "unmapped"])
    dump_csv(args.out / "report_confusions.csv", confusions)
    dump_csv(args.out / "sv_exclusion_sensitivity.csv", sensitivity)


if __name__ == "__main__":
    main()
