"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from numbers import Real
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item
from lab9.graders import GRADERS


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems: list[str] = []
    metrics = pr.get("metrics") or {}
    for name, value in metrics.items():
        if isinstance(value, Real) and not isinstance(value, bool) and not math.isfinite(float(value)):
            problems.append(f"metric {name} is not finite")

    rows = pr.get("rows") or []
    base_rows = base.get("rows") or []
    manifest = pr.get("manifest") or {}
    expected = None
    if isinstance(manifest.get("items"), int) and isinstance(manifest.get("seeds"), list):
        expected = manifest["items"] * len(manifest["seeds"])
        if len(rows) != expected:
            problems.append(f"row count {len(rows)} != manifest items × seeds ({expected})")

    pairs = [(row.get("item_id"), row.get("seed")) for row in rows]
    pair_set = set(pairs)
    if len(pair_set) != len(pairs):
        problems.append("duplicate (item_id, seed) rows")
    base_pairs = {(row.get("item_id"), row.get("seed")) for row in base_rows}
    if pair_set != base_pairs:
        problems.append("(item_id, seed) rows differ from baseline")

    if pr.get("evaluator_failures"):
        problems.append(f"evaluator_failures is non-empty ({len(pr['evaluator_failures'])})")
    graded = [m["id"] for m in spec.get("metrics", []) if m.get("id") in GRADERS]
    missing_values = sorted({mid for row in rows for mid in graded if row.get(mid) is None})
    problems += [f"graded metric {mid} has a missing row value" for mid in missing_values]
    non_finite_rows = sorted({f"{row.get('item_id')}@{row.get('seed')}:{mid}"
                              for row in rows for mid in graded
                              if isinstance(row.get(mid), Real) and not isinstance(row.get(mid), bool)
                              and not math.isfinite(float(row[mid]))})
    problems += [f"graded row value is not finite ({key})" for key in non_finite_rows]

    def item_slices(report_rows: list[dict]) -> tuple[dict[str, frozenset[str]], list[str]]:
        by_item: dict[str, set[frozenset[str]]] = {}
        for row in report_rows:
            item_id = row.get("item_id")
            if item_id is not None:
                by_item.setdefault(str(item_id), set()).add(frozenset(row.get("slices") or []))
        inconsistent = sorted(item for item, tags in by_item.items() if len(tags) > 1)
        return {item: next(iter(tags)) for item, tags in by_item.items() if len(tags) == 1}, inconsistent

    pr_slices, pr_inconsistent = item_slices(rows)
    base_slices, base_inconsistent = item_slices(base_rows)
    problems += [f"item {item} has inconsistent slice tags across PR rows" for item in pr_inconsistent]
    problems += [f"baseline item {item} has inconsistent slice tags" for item in base_inconsistent]
    changed_slices = sorted(item for item in set(pr_slices) | set(base_slices)
                            if pr_slices.get(item) != base_slices.get(item))
    problems += [f"item {item} slice tags differ from baseline" for item in changed_slices]

    if base_spec is not None and spec.get("eval_set_version") == base_spec.get("eval_set_version"):
        def index(entries: list[dict], key: str) -> dict[str, dict]:
            return {str(entry[key]): entry for entry in entries if key in entry}

        def check_ratchet(kind: str, old: dict, new: dict) -> None:
            for name, previous in old.items():
                current = new.get(name)
                if current is None:
                    problems.append(f"ratchet: {kind} {name} disappeared")
                    continue
                if previous.get("blocking") and not current.get("blocking"):
                    problems.append(f"ratchet: {kind} {name} became non-blocking")
                old_th, new_th = previous.get("threshold") or {}, current.get("threshold") or {}
                if "min" in old_th and ("min" not in new_th or new_th["min"] < old_th["min"]):
                    problems.append(f"ratchet: {kind} {name} minimum threshold loosened")
                if "max" in old_th and ("max" not in new_th or new_th["max"] > old_th["max"]):
                    problems.append(f"ratchet: {kind} {name} maximum threshold loosened")
                if old_th.get("no_significant_drop") and not new_th.get("no_significant_drop"):
                    problems.append(f"ratchet: {kind} {name} dropped no_significant_drop")

        check_ratchet("metric", index(base_spec.get("metrics", []), "id"),
                      index(spec.get("metrics", []), "id"))
        check_ratchet("slice", index(base_spec.get("slices", []), "name"),
                      index(spec.get("slices", []), "name"))
    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked: list[str] = []
    lines: list[str] = []
    bs = spec.get("bootstrap", {})
    for entry in spec.get("slices", []):
        name, metric = entry["name"], entry["metric"]
        pr_values = per_item(pr, metric, name)
        base_values = per_item(base, metric, name)
        value = sum(pr_values.values()) / len(pr_values) if pr_values else None
        verdicts: list[str] = []
        note = ""
        if value is None or not base_values:
            verdicts.append("missing slice items")
        if value is not None and "min" in entry and value < entry["min"]:
            verdicts.append(f"below min {entry['min']}")
        if entry.get("no_significant_drop") and pr_values and base_values:
            keys = sorted(set(pr_values) & set(base_values))
            if not keys:
                verdicts.append("no paired slice items")
            else:
                d, lo, hi = stats.paired_bootstrap(
                    [pr_values[k] for k in keys], [base_values[k] for k in keys],
                    n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027),
                    confidence=bs.get("confidence", 0.95))
                note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                if hi < 0:
                    verdicts.append("significant drop")
        metric_id = f"slice:{name}/{metric}"
        is_blocked = bool(verdicts) and entry.get("blocking", False)
        if is_blocked:
            blocked.append(metric_id)
        label = "BLOCK" if is_blocked else ("warn" if verdicts else "ok")
        lines.append(f"  {metric_id:<38} {value!s:<8} {note:<28} {', '.join(verdicts):<24} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
