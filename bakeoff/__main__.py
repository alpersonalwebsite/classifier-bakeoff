"""Command line: `uv run python -m bakeoff <command>`."""

import argparse
import json
import os
import sys
from pathlib import Path

from . import conclusions
from . import dataset as ds
from .report import load_withheld, render
from .runner import RESULTS_DIR, run
from .scoring import all_four_shares, load_run, score_run
from .variants import BY_NAME, DEFAULT_CAP_USD, VARIANTS, load_prices

ROOT = Path(__file__).resolve().parent.parent
PUBLIC_DIR = ROOT / "reports" / "public"
FULL_DIR = ROOT / "reports" / "full"


def load_env(path: Path = ROOT / ".env") -> None:
    """Load KEY=value lines into the environment without printing any of them."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def write_reports(run_dir: Path) -> tuple[Path, Path]:
    meta, records = load_run(run_dir)
    dataset, version = ds.load_frozen()
    if version != meta["dataset_version"]:
        sys.exit(f"run {meta['run_id']} used dataset {meta['dataset_version']}, the frozen one is {version}")
    scores = score_run(meta, records, dataset)
    withheld = load_withheld()
    dataset_meta = json.loads(ds.META_FILE.read_text())
    # Spec 003 B6: results under the labels as generated beside the labels as frozen.
    original = ds.original_rows(dataset)
    label_dependence = None
    if original is not None:
        before, after = all_four_shares(meta, records, original), all_four_shares(meta, records, dataset)
        label_dependence = {n: (before[n], after[n]) for n in after if n in before}
    args = dict(meta=meta, scores=scores, withheld=withheld, dataset_meta=dataset_meta, label_dependence=label_dependence)
    # Spec 002: conclusions belong to one run, and every figure they quote must be in
    # that run's public edition as it reads without them. Check before writing anything.
    text = conclusions.load(meta["run_id"])
    body = None
    if text is not None:
        problems = conclusions.check(text, render(public=True, **args))
        if problems:
            raise conclusions.ConclusionsError(
                f"conclusions for {meta['run_id']} quote figures the report does not support; no report written:\n  "
                + "\n  ".join(problems)
            )
        body = conclusions.to_html(text)
    full_html = render(public=False, conclusions_html=body, **args)
    public_html = render(public=True, conclusions_html=body, **args)
    FULL_DIR.mkdir(parents=True, exist_ok=True)
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    full = FULL_DIR / f"{meta['run_id']}.html"
    public = PUBLIC_DIR / f"{meta['run_id']}.html"
    full.write_text(full_html, encoding="utf-8")
    public.write_text(public_html, encoding="utf-8")
    return full, public


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="bakeoff")
    sub = parser.add_subparsers(dest="command", required=True)
    g = sub.add_parser("generate", help="write data/candidate.jsonl with the generator model")
    g.add_argument("--seed", type=int, default=7)
    sub.add_parser("check", help="check data/candidate.jsonl")
    sub.add_parser("freeze", help="check and freeze data/candidate.jsonl as data/dataset.jsonl")
    r = sub.add_parser("run", help="run variants over the frozen dataset, then write both reports")
    r.add_argument("--variant", action="append", choices=list(BY_NAME), help="repeat to pick several; default all")
    r.add_argument("--cap", type=float, default=DEFAULT_CAP_USD, help="spend cap per variant in USD")
    r.add_argument("--limit", type=int, help="first N messages only, for a smoke test (reported as partial)")
    rep = sub.add_parser("report", help="rebuild both reports from a saved run, no provider calls")
    rep.add_argument("run_dir", nargs="?", type=Path, help="default: the latest run")
    args = parser.parse_args(argv)

    if args.command == "generate":
        load_env()
        rows = ds.generate(ds.build_specs(args.seed))
        ds.write_jsonl(ds.CANDIDATE_FILE, rows)
        print(f"wrote {ds.CANDIDATE_FILE.relative_to(ROOT)}")
        args.command = "check"
    if args.command == "check":
        problems = ds.check_dataset(ds.read_jsonl(ds.CANDIDATE_FILE))
        print("\n".join(problems) if problems else "candidate passes every check; review it, then run `freeze`")
        sys.exit(1 if problems else 0)
    if args.command == "freeze":
        print(f"frozen as {ds.freeze()}")
    if args.command == "run":
        load_env()
        dataset, version = ds.load_frozen()
        if args.limit:
            dataset = dataset[: args.limit]
        variants = [BY_NAME[n] for n in args.variant] if args.variant else list(VARIANTS)
        run_dir = run(variants, dataset, version, load_prices(), cap_usd=args.cap)
        print(f"results in {run_dir.relative_to(ROOT)}")
        if args.limit:
            print("smoke test: reports skipped, since they score against the full dataset")
            return
        args.command, args.run_dir = "report", run_dir
    if args.command == "report":
        run_dir = args.run_dir or max(RESULTS_DIR.iterdir(), key=lambda p: p.name)
        full, public = write_reports(run_dir)
        print(f"full edition (local only): {full.relative_to(ROOT)}\npublic edition: {public.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
