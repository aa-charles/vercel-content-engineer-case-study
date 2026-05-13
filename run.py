"""
run.py — pipeline orchestrator.

Sequential execution of extract → compare → draft, with progress indicators,
cost estimates, a human review checkpoint between compare and draft, and
graceful failure handling.

Usage:
  python3 run.py                                  # full pipeline
  python3 run.py --skip-extract                   # reuse extractions
  python3 run.py --skip-extract --skip-compare    # only re-draft
  python3 run.py --no-review                      # no checkpoint (unattended)
  python3 run.py --status                         # show outputs state, exit
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from utils import output_path

ROOT        = Path(__file__).parent
OUTPUTS     = ROOT / "outputs"
EXTRACTIONS_PATH    = output_path("extractions")
MATRIX_PATH         = output_path("comparison_matrix")
BRIEF_PATH          = output_path("comparison_brief")
DRAFT_PATH          = output_path("agent_draft")
REVISION_NOTES_PATH = output_path("agent_draft_revision_notes")
RAW         = OUTPUTS / "raw"

# Estimates from prior runs. NOT measurements — agents don't currently
# instrument token usage. Used only for the orchestrator's display.
EST_COST = {
    "extract": (1.40, 1.40),
    "compare": (4.00, 6.00),
    "draft":   (2.00, 3.00),
}
EST_TIME = {"extract": "~5-7 min", "compare": "~5-10 min", "draft": "~5-8 min"}

BAR   = "─" * 95
HEAVY = "═" * 95


# ─────────────────────────── formatting helpers ───────────────────────────

def _fmt_seconds(s: float) -> str:
    if s < 60:
        return f"{s:.0f}s"
    m, sec = divmod(s, 60)
    return f"{int(m)}m {int(sec)}s"


def _fmt_mtime(path: Path) -> str:
    if not path.exists():
        return "—"
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")


def _fmt_cost(cost_tuple) -> str:
    """Format a (low, high) cost tuple as '~$X.XX' if equal, '~$X.XX-Y.YY' otherwise."""
    low, high = cost_tuple
    if low == high:
        return f"~${low:.2f}"
    return f"~${low:.2f}-{high:.2f}"


def _word_count(path: Path):
    return len(path.read_text().split()) if path.exists() else None


# ─────────────────────────── metric extractors ────────────────────────────

def _extract_metric():
    if not EXTRACTIONS_PATH.exists():
        return None
    data = json.loads(EXTRACTIONS_PATH.read_text())
    n_claims  = sum(len(e.get("claims", [])) for e in data.get("extractions", []))
    n_sources = len(data.get("extractions", []))
    return f"{n_claims} claims, {n_sources} sources"


def _compare_metric():
    if not MATRIX_PATH.exists():
        return None
    data = json.loads(MATRIX_PATH.read_text())
    return (
        f"{len(data.get('dimensions', {}))} dimensions, "
        f"{len(data.get('editorial_tensions', []))} tensions, "
        f"{len(data.get('detected_asymmetries', []))} asymmetries"
    )


def _voice_anchor_summary():
    """Returns (description, cache_exists, cache_path) or (error_msg, False, None)."""
    try:
        from prompt_context import _parse_voice_anchor_section, _select_voice_anchor
        from utils import RAW_DIR, slug
        sources      = json.loads((ROOT / "sources.json").read_text())
        brief_anchor = _parse_voice_anchor_section((ROOT / "piece_brief.md").read_text())
        selected     = _select_voice_anchor(brief_anchor, sources["style_references"])
        matches = [
            r for r in sources["style_references"]
            if r.get("genre") == brief_anchor.get("genre")
            and r.get("subject_domain") == brief_anchor.get("subject_domain")
        ]
        basis = "exact subject_domain match" if matches else "primary_voice_anchor fallback"
        name = selected["url"].rstrip("/").split("/")[-1]
        cache_path = RAW_DIR / f"{slug(selected['url'])}.txt"
        return f"{name} — selected via {basis}", cache_path.exists(), cache_path
    except Exception as e:
        return f"could not determine ({e})", False, None


def _suggest_next_command() -> str:
    """Suggest the next run.py invocation based on which outputs exist."""
    if not EXTRACTIONS_PATH.exists():
        return "python3 run.py"
    if not MATRIX_PATH.exists():
        return "python3 run.py --skip-extract"
    if not DRAFT_PATH.exists():
        return "python3 run.py --skip-extract --skip-compare"
    return "(all outputs present — full pipeline already complete)"


# ─────────────────────────── --status mode ────────────────────────────────

def _print_row(symbol: str, name: str, mtime: str, metric: str = ""):
    print(f"    {symbol} {name:<72} {mtime:<18} {metric}")


def show_status():
    print(BAR)
    print(f"PIPELINE STATUS  —  {OUTPUTS.relative_to(ROOT)}/")
    print(BAR)

    print("\n  Extract:")
    if EXTRACTIONS_PATH.exists():
        _print_row("✓", EXTRACTIONS_PATH.name, _fmt_mtime(EXTRACTIONS_PATH), _extract_metric() or "")
    else:
        _print_row("✗", EXTRACTIONS_PATH.name, "not generated")

    print("\n  Compare:")
    if MATRIX_PATH.exists():
        _print_row("✓", MATRIX_PATH.name, _fmt_mtime(MATRIX_PATH), _compare_metric() or "")
        if BRIEF_PATH.exists():
            _print_row("✓", BRIEF_PATH.name, _fmt_mtime(BRIEF_PATH), f"~{_word_count(BRIEF_PATH):,} words")
    else:
        _print_row("✗", MATRIX_PATH.name, "not generated")
        _print_row("✗", BRIEF_PATH.name, "not generated")

    print("\n  Draft:")
    if DRAFT_PATH.exists():
        _print_row("✓", DRAFT_PATH.name, _fmt_mtime(DRAFT_PATH), f"~{_word_count(DRAFT_PATH):,} words")
        _print_row("✓", REVISION_NOTES_PATH.name, _fmt_mtime(REVISION_NOTES_PATH), f"~{_word_count(REVISION_NOTES_PATH):,} words")
    else:
        _print_row("✗", DRAFT_PATH.name, "not generated")
        _print_row("✗", REVISION_NOTES_PATH.name, "not generated")

    print("\n  Voice anchor (will be used at next draft):")
    desc, cache_exists, cache_path = _voice_anchor_summary()
    print(f"    {desc}")
    if cache_path is not None:
        if cache_exists:
            print(f"    cache: ✓ {cache_path.name} ({cache_path.stat().st_size:,} bytes)")
        else:
            print(f"    cache: ✗ not cached (will fetch on first draft run)")

    print("\n  Cached source pages:")
    if RAW.exists():
        files = list(RAW.glob("*.txt"))
        total = sum(f.stat().st_size for f in files)
        print(f"    {len(files)} files in outputs/raw/  ({total:,} bytes total)")
    else:
        print("    none yet")

    print(f"\n  Suggested next command:  {_suggest_next_command()}\n")


# ─────────────────────────── stage runners ────────────────────────────────

def stage_banner(num: int, name: str, skipped: bool = False):
    print()
    print(BAR)
    if skipped:
        print(f"[{num}/3] {name.upper()}  —  SKIPPED (using existing output)")
    else:
        print(f"[{num}/3] {name.upper()}  —  estimated {_fmt_cost(EST_COST[name])}, {EST_TIME[name]}")
    print(BAR)
    print()


def stage_done(num: int, name: str, elapsed: float):
    print()
    print(f"[{num}/3] {name.upper()} — done in {_fmt_seconds(elapsed)} ✓")


def stage_failed(num: int, name: str, elapsed: float, exc: Exception):
    print()
    print(BAR)
    print(f"[{num}/3] {name.upper()} — FAILED after {_fmt_seconds(elapsed)}")
    print(BAR)
    print()
    print(f"  {type(exc).__name__}: {exc}")
    print()


def review_checkpoint():
    print()
    print(BAR)
    print("REVIEW CHECKPOINT")
    print(BAR)
    print()
    print("Compare stage complete. Review the comparison brief before drafting:")
    print()
    print(f"  open {BRIEF_PATH.relative_to(ROOT)}")
    print()
    print("Press ENTER to continue to draft stage, or Ctrl-C to abort.")
    try:
        input("> ")
    except EOFError:
        # Piped/empty stdin should abort cleanly, not crash. Treat as user abort.
        raise KeyboardInterrupt


def run_stage(num: int, name: str, fn) -> float:
    """Run a stage, time it, return elapsed seconds. Re-raises on failure
    after printing the failure banner."""
    stage_banner(num, name)
    t0 = time.perf_counter()
    try:
        fn()
    except Exception as e:
        stage_failed(num, name, time.perf_counter() - t0, e)
        raise
    elapsed = time.perf_counter() - t0
    stage_done(num, name, elapsed)
    return elapsed


# ─────────────────────────── final summary ────────────────────────────────

def final_summary(timings: dict, completed: list, voice_anchor_desc: str):
    print()
    print(HEAVY)
    print("PIPELINE COMPLETE")
    print(HEAVY)
    print()
    print("  Stage     Time      Est. cost      Output")
    print("  ───────   ───────   ────────────   ──────────────────────────────────")

    rows = [
        ("extract", [EXTRACTIONS_PATH]),
        ("compare", [MATRIX_PATH, BRIEF_PATH]),
        ("draft",   [DRAFT_PATH, REVISION_NOTES_PATH]),
    ]
    for name, outputs in rows:
        t = timings.get(name)
        time_str = _fmt_seconds(t) if t else "skipped"
        cost_str = _fmt_cost(EST_COST[name]) if t else "—"
        for i, out in enumerate(outputs):
            label_time = time_str if i == 0 else ""
            label_cost = cost_str if i == 0 else ""
            label_name = name.capitalize() if i == 0 else ""
            out_str = str(out.relative_to(ROOT)) if out.exists() else "—"
            print(f"  {label_name:<8}  {label_time:<8}  {label_cost:<12}  {out_str}")

    total = sum(timings.values())
    total_low  = sum(EST_COST[name][0] for name in completed)
    total_high = sum(EST_COST[name][1] for name in completed)
    print()
    print(f"  Total time:           {_fmt_seconds(total)}")
    print(f"  Total estimated cost: {_fmt_cost((total_low, total_high))}")
    print(f"    (range reflects variation by corpus size, claim density, and revision")
    print(f"     length; actual cost not instrumented)")

    if "draft" in completed and voice_anchor_desc:
        print()
        print(f"  Voice anchor: {voice_anchor_desc}")

    if DRAFT_PATH.exists():
        print()
        print(f"  Final draft:  {DRAFT_PATH.relative_to(ROOT)}")
    print()


# ─────────────────────────── main ─────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(
        description="Comparison article pipeline: extract → compare → draft.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 run.py                                  # full pipeline\n"
            "  python3 run.py --skip-extract                   # reuse extractions\n"
            "  python3 run.py --skip-extract --skip-compare    # only re-draft\n"
            "  python3 run.py --no-review                      # no checkpoint (unattended)\n"
            "  python3 run.py --status                         # show outputs state, exit"
        ),
    )
    p.add_argument("--skip-extract", action="store_true", help="skip extract stage (requires existing extractions.json)")
    p.add_argument("--skip-compare", action="store_true", help="skip compare stage (requires existing comparison_matrix.json)")
    p.add_argument("--skip-draft",   action="store_true", help="skip draft stage")
    p.add_argument("--no-review",    action="store_true", help="skip the human review checkpoint")
    p.add_argument("--status",       action="store_true", help="show outputs state without running")
    args = p.parse_args()

    if args.status:
        show_status()
        return

    if args.skip_extract and args.skip_compare and args.skip_draft:
        print("All stages skipped — nothing to do.", file=sys.stderr)
        sys.exit(1)

    # Fail-fast on missing inputs for skipped stages
    if args.skip_extract and not EXTRACTIONS_PATH.exists():
        print(f"--skip-extract requires {EXTRACTIONS_PATH.relative_to(ROOT)} to exist.", file=sys.stderr)
        print("Run extract first or remove the flag.", file=sys.stderr)
        sys.exit(1)
    if args.skip_compare and not MATRIX_PATH.exists():
        print(f"--skip-compare requires {MATRIX_PATH.relative_to(ROOT)} to exist.", file=sys.stderr)
        print("Run compare first or remove the flag.", file=sys.stderr)
        sys.exit(1)

    timings   = {}
    completed = []

    try:
        if not args.skip_extract:
            import agent_extract
            timings["extract"] = run_stage(1, "extract", agent_extract.run)
            completed.append("extract")
        else:
            stage_banner(1, "extract", skipped=True)

        if not args.skip_compare:
            import agent_compare
            timings["compare"] = run_stage(2, "compare", agent_compare.run)
            completed.append("compare")
        else:
            stage_banner(2, "compare", skipped=True)

        # Review checkpoint — only when compare just ran AND draft will run
        if not args.skip_draft and not args.no_review and not args.skip_compare:
            review_checkpoint()

        if not args.skip_draft:
            import agent_draft
            timings["draft"] = run_stage(3, "draft", agent_draft.run)
            completed.append("draft")
        else:
            stage_banner(3, "draft", skipped=True)

    except KeyboardInterrupt:
        print("\n\nPipeline aborted by user.")
        if completed:
            print("Completed stages keep their outputs:")
            if "extract" in completed:
                print(f"  ✓ {EXTRACTIONS_PATH.relative_to(ROOT)}")
            if "compare" in completed:
                print(f"  ✓ {MATRIX_PATH.relative_to(ROOT)}")
                print(f"  ✓ {BRIEF_PATH.relative_to(ROOT)}")
            print()
            print(f"To resume: {_suggest_next_command()}")
        sys.exit(130)
    except Exception:
        # stage_failed banner already printed inside run_stage
        print("Pipeline stopped. Completed stages keep their outputs.")
        if completed:
            print()
            for name in completed:
                primary = {"extract": EXTRACTIONS_PATH, "compare": MATRIX_PATH, "draft": DRAFT_PATH}[name]
                print(f"  ✓ {primary.relative_to(ROOT)} (from {name})")
        print()
        print(f"To retry: {_suggest_next_command()}")
        sys.exit(1)

    # Voice anchor summary line (only meaningful if draft ran)
    voice_anchor_desc = ""
    if "draft" in completed:
        desc, _, _ = _voice_anchor_summary()
        voice_anchor_desc = desc

    final_summary(timings, completed, voice_anchor_desc)


if __name__ == "__main__":
    main()
