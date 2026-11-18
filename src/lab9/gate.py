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
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, aggregate, load_spec, per_item


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
    rows, base_rows = pr.get("rows") or [], base.get("rows") or []
    man, base_man = pr.get("manifest") or {}, base.get("manifest") or {}

    # 1. Metric values must be finite numbers (NaN compares False against every threshold).
    for k, v in (pr.get("metrics") or {}).items():
        if isinstance(v, float) and not math.isfinite(v):
            problems.append(f"metric {k} is {v} (NaN/inf compares False against any threshold)")

    # 2. Graders must not have crashed: no evaluator failures, no missing value for a graded metric.
    if pr.get("evaluator_failures"):
        problems.append(f"{len(pr['evaluator_failures'])} evaluator failure(s) in the report: "
                        f"{str(pr['evaluator_failures'][0])[:80]}")
    graded = _row_metrics(spec, base_rows or rows)
    missing = [(r.get("item_id"), r.get("seed"), m) for r in rows for m in graded
               if not isinstance(r.get(m), bool)]
    if missing:
        i, s, m = missing[0]
        problems.append(f"{len(missing)} graded value(s) missing or not bool (first {i}@{s} {m}); "
                        "a crashed grader must not drop out of the mean")

    # 3. Rows cover exactly items x seeds, once each, and the same (item, seed) set as the baseline.
    keys = [(r.get("item_id"), r.get("seed")) for r in rows]
    dupes = sorted({k for k in keys if keys.count(k) > 1}, key=str)
    if dupes:
        problems.append(f"{len(dupes)} duplicated (item, seed) row(s), first {dupes[0]}")
    want_n = int(man.get("items") or 0) * len(man.get("seeds") or [])
    if len(rows) != want_n:
        problems.append(f"{len(rows)} rows, manifest says {man.get('items')} items x "
                        f"{len(man.get('seeds') or [])} seeds = {want_n}")
    if base_man and (man.get("items"), sorted(man.get("seeds") or [])) != (base_man.get("items"), sorted(base_man.get("seeds") or [])):
        problems.append(f"manifest items/seeds {man.get('items')}/{man.get('seeds')} differ from the "
                        f"baseline's {base_man.get('items')}/{base_man.get('seeds')}")
    if spec.get("seeds") and sorted(man.get("seeds") or []) != sorted(spec["seeds"]):
        problems.append(f"report seeds {man.get('seeds')} differ from the spec's {spec['seeds']}")
    if base_rows:
        have, want = set(keys), {(r.get("item_id"), r.get("seed")) for r in base_rows}
        if have != want:
            problems.append(f"(item, seed) set differs from the baseline: {len(want - have)} missing, "
                            f"{len(have - want)} extra (dropped or cherry-picked rows)")

    # 4. Reported aggregates must be what the rows say (a hand-edited or stale metrics block).
    if rows and graded:
        has_cost = all("cost" in r for r in rows)
        try:
            again = aggregate([r if has_cost else {**r, "cost": 0.0} for r in rows],
                              [m for m in graded if all(m in r for r in rows)],
                              k_values=spec.get("pass_k", []))
        except Exception as e:                       # malformed rows are themselves a problem
            problems.append(f"cannot recompute metrics from rows: {e!r}")
        else:
            if not has_cost:
                again.pop("cost_per_success", None)
            for k, v in again.items():
                got = (pr.get("metrics") or {}).get(k, v)
                if isinstance(v, (int, float)) and isinstance(got, (int, float)) and math.isfinite(got):
                    if abs(float(got) - float(v)) > 1e-4:
                        problems.append(f"metric {k} reported {got} but rows give {v}")
                elif (v is None) != (got is None):
                    problems.append(f"metric {k} reported {got} but rows give {v}")

    # 5. Slice tags come from labels; an item may not move in or out of a slice between runs.
    base_tags = {r.get("item_id"): sorted(r.get("slices") or []) for r in base_rows}
    moved = sorted({r.get("item_id") for r in rows
                    if r.get("item_id") in base_tags and sorted(r.get("slices") or []) != base_tags[r.get("item_id")]},
                   key=str)
    if moved:
        problems.append(f"slice tags differ from the baseline for {len(moved)} item(s), first {moved[0]}")

    # 6. Ratchet: on the same eval-set version thresholds may only get stricter.
    if base_spec is not None:
        problems += _ratchet(spec, base_spec)
    return problems


def _row_metrics(spec: dict, rows: list[dict]) -> list[str]:
    """Spec metrics graded per row (present in the reference rows), e.g. pass_rate, secret_leak."""
    in_rows = set().union(*(r.keys() for r in rows)) if rows else set()
    return [m["id"] for m in spec.get("metrics") or [] if m["id"] in in_rows]


def _ratchet(spec: dict, base_spec: dict) -> list[str]:
    if spec.get("eval_set_version") != base_spec.get("eval_set_version"):
        return []                                    # new eval-set version: thresholds start over
    out: list[str] = []

    def compare(where: str, new: dict | None, old: dict) -> None:
        if new is None:
            out.append(f"ratchet: {where} was removed")
            return
        if old.get("blocking") and not new.get("blocking"):
            out.append(f"ratchet: {where} is no longer blocking")
        th_new = new.get("threshold", new) if "threshold" in old else new
        th_old = old.get("threshold", old)
        for key in ("max", "max_increase"):
            if key in th_old and (key not in th_new or th_new[key] > th_old[key]):
                out.append(f"ratchet: {where} {key} loosened {th_old[key]} -> {th_new.get(key, 'removed')}")
        if "min" in th_old and ("min" not in th_new or th_new["min"] < th_old["min"]):
            out.append(f"ratchet: {where} min loosened {th_old['min']} -> {th_new.get('min', 'removed')}")
        if th_old.get("no_significant_drop") and not th_new.get("no_significant_drop"):
            out.append(f"ratchet: {where} dropped no_significant_drop")

    new_metrics = {m["id"]: m for m in spec.get("metrics") or []}
    for m in base_spec.get("metrics") or []:
        compare(f"metric {m['id']}", new_metrics.get(m["id"]), m)
    new_slices = {(s["name"], s["metric"]): s for s in spec.get("slices") or []}
    for s in base_spec.get("slices") or []:
        compare(f"slice {s['name']}/{s['metric']}", new_slices.get((s["name"], s["metric"])), s)
    for key in ("eval_set", "labels", "seeds", "adversarial_pack"):
        if key in base_spec and spec.get(key) != base_spec[key]:
            out.append(f"ratchet: {key} changed on the same eval-set version")
    bs_new, bs_old = spec.get("bootstrap") or {}, base_spec.get("bootstrap") or {}
    if bs_new.get("confidence", 0.95) < bs_old.get("confidence", 0.95):
        out.append("ratchet: bootstrap confidence lowered")
    return out


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
    for s in spec.get("slices") or []:
        name, metric = s["name"], s["metric"]
        sid = f"slice:{name}/{metric}"
        a, b = per_item(pr, metric, slice_name=name), per_item(base, metric, slice_name=name)
        verdict, note, val = "ok", "", None
        if not a:
            verdict = "missing"            # a slice the spec gates on must have rows; empty = cannot vouch
        else:
            val = round(sum(a.values()) / len(a), 4)
            if "min" in s and val < s["min"]:
                verdict = "fail"
            keys = sorted(set(a) & set(b))
            if s.get("no_significant_drop") and keys:
                d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                                   n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027),
                                                   confidence=bs.get("confidence", 0.95))
                note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                if hi < 0:
                    verdict = "fail"
        if verdict != "ok" and s.get("blocking"):
            blocked.append(sid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if s.get("blocking") else "warn")
        th = {k: s[k] for k in ("min", "no_significant_drop") if k in s}
        lines.append(f"  {sid:<34} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}  (n_items={len(a)})")
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
