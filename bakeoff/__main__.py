"""Command line: `uv run python -m bakeoff <command>`."""

import argparse
import json
import os
import sys
from pathlib import Path

from . import conclusions, definitions, labeling, relabel
from . import dataset as ds
from .questions import QUESTIONS
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


def latest_run() -> Path:
    """The newest saved run under the current definitions. results/ also holds labeling pages and
    relabel calls, which have no run.json, and runs under another definition set (spec 005), which
    are compared in the current run's report and never scored against the frozen labels on their own.
    Runs from before question sets were recorded carry none and were all under the current text."""
    runs = sorted(RESULTS_DIR.glob("*/run.json")) if RESULTS_DIR.exists() else []
    runs = [p for p in runs if json.loads(p.read_text()).get("question_set", "current") == "current"]
    if not runs:
        sys.exit("no saved run under the current definitions in results/; run one first, or pass a run directory")
    return runs[-1].parent


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
    # Spec 004: the independent relabeling, when one is on record.
    relabel_view = None
    record = relabel.load()
    if record is not None:
        relabel.check_independent(record, meta.get("models", {}))
        edits = relabel.edited_labels()
        alt = score_run(meta, records, relabel.with_rater_on_edits(dataset, record, edits))
        relabel_view = {
            "record": record,
            "agreement": relabel.agreement(record, dataset, edits),
            "ranked": [s for s in alt if s.complete],
            "edited_count": len(edits),
        }
    # Spec 005: the same run against the outside labels, and the run under the outside definitions.
    outside_view = None
    if definitions.SET_FILE.exists() and relabel.OUTSIDE_FILE.exists():
        drec = json.loads(definitions.SET_FILE.read_text())
        lrec = json.loads(relabel.OUTSIDE_FILE.read_text())
        out_data = relabel.outside_dataset(dataset, lrec)
        full = None
        if drec.get("run_id") and (RESULTS_DIR / drec["run_id"]).exists():
            ometa, orecs = load_run(RESULTS_DIR / drec["run_id"])
            full = [s for s in score_run(ometa, orecs, out_data) if s.complete]
        labeled = list(lrec["labels"].values())
        outside_view = {
            "definitions": drec,
            "mid": [s for s in score_run(meta, records, out_data) if s.complete],
            "full": full,
            "notes": {
                "two_intent": sum(len(v["intent"]) == 2 for v in labeled),
                "frozen_two_intent": sum(len(m["truth"]["intent"]) == 2 for m in dataset),
                "contact_no": sum(v["wants_contact"] == ["no"] for v in labeled),
                "frozen_contact_no": sum(m["truth"]["wants_contact"] == ["no"] for m in dataset if m["id"] in lrec["labels"]),
                "labeled": len(labeled),
                "left_out": len(dataset) - len(labeled),
            },
        }
    # Spec 007: every human blind labeling on record.
    human_view = []
    truth = {m["id"]: m["truth"] for m in dataset}
    edits_all = relabel.edited_labels()
    for rec in labeling.load_all():
        agree = {q.name: sum(labeling.matches(rec["labels"][mid][q.name], truth[mid][q.name]) for mid in rec["labels"]) for q in QUESTIONS}
        view = {"record": rec, "agree": agree, "n": len(rec["labels"]),
                "ranked": [s for s in score_run(meta, records, labeling.with_labels(dataset, rec, edits_all)) if s.complete],
                "second": labeling.second_look_counts(rec["second_look"]) if rec.get("second_look") else None}
        if rec["set"] == "edits":
            view["edits"] = labeling.edits_agreement(rec, dataset, edits_all)
            rater = relabel.load()
            view["rater"] = relabel.agreement(rater, dataset, edits_all) if rater else None
        human_view.append(view)
    args = dict(
        meta=meta, scores=scores, withheld=withheld, dataset_meta=dataset_meta,
        label_dependence=label_dependence, relabel=relabel_view, outside=outside_view, human=human_view,
    )
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
    r.add_argument("--question-set", default="current", help="definition set under data/definitions/ (spec 005); default: current")
    sub.add_parser("relabel", help="blind outside-model relabeling of the edited messages (spec 004); costs money")
    lp = sub.add_parser("label-page", help="write the local blind labeling page (spec 007); no key, no cost")
    lp.add_argument("--set", choices=labeling.SETS, default="edits", help="edits: if you have not followed the review; unseen: if you have")
    li = sub.add_parser("label-import", help="import a saved labels file under your chosen name")
    li.add_argument("file", type=Path)
    li.add_argument("--name", required=True, help="a handle for your labeling: lowercase letters, digits, hyphens")
    ls = sub.add_parser("label-second-look", help="write the local second-look page for your disagreements")
    ls.add_argument("--name", required=True)
    lsum = sub.add_parser("label-summary", help="show a labeling's results from committed data; works from a fresh clone")
    lsum.add_argument("--name", required=True)
    l2 = sub.add_parser("label-import-second", help="import a saved second-look file")
    l2.add_argument("file", type=Path)
    l2.add_argument("--name", required=True)
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
        run_dir = run(variants, dataset, version, load_prices(), cap_usd=args.cap, question_set=args.question_set)
        print(f"results in {run_dir.relative_to(ROOT)}")
        if args.limit:
            print("smoke test: reports skipped, since they score against the full dataset")
            return
        args.command, args.run_dir = "report", run_dir
    if args.command == "relabel":
        load_env()
        dataset, _ = ds.load_frozen()
        items = relabel.blind_set(dataset, relabel.edited_labels())
        record = relabel.run(items)
        relabel.RELABEL_DIR.mkdir(parents=True, exist_ok=True)
        relabel.RELABEL_FILE.write_text(json.dumps(record, indent=2) + "\n")
        print(f"labeled {len(record['labels'])} of {len(items)}, failed {len(record['failed'])}, cost ${record['cost_usd']:.4f}")
        print(f"served by {record['served_by']}, model {record['models_reported']}; wrote {relabel.RELABEL_FILE.relative_to(ROOT)}")
        return
    if args.command == "label-summary":
        dataset, _ = ds.load_frozen()
        path = labeling.record_path(args.name)
        if not path.exists():
            sys.exit(f"no labeling named {args.name!r}; import one with label-import first")
        record = json.loads(path.read_text())
        sl = labeling.second_look_path(args.name)
        record["second_look"] = json.loads(sl.read_text()) if sl.exists() else None
        print(labeling.summary(record, dataset, relabel.edited_labels(), relabel.load()))
        return
    if args.command in ("label-page", "label-import", "label-second-look", "label-import-second"):
        dataset, _ = ds.load_frozen()
        labeling.WORK_DIR.mkdir(parents=True, exist_ok=True)
        labeling.HUMAN_DIR.mkdir(parents=True, exist_ok=True)
        if args.command == "label-page":
            items = labeling.blind_set(dataset, args.set)
            page = labeling.WORK_DIR / f"labeling-{args.set}.html"
            page.write_text(labeling.first_page(items, args.set), encoding="utf-8")
            print(f"open {page} in a browser: {len(items)} messages ({args.set} set)")
        elif args.command == "label-import":
            path = labeling.record_path(args.name)
            if path.exists():
                sys.exit(f"{path.relative_to(ROOT)} already exists; choose another name")
            record = labeling.import_first(dataset, json.loads(args.file.read_text()), args.name)
            path.write_text(json.dumps(record, indent=2) + "\n")
            print(f"imported {len(record['labels'])} messages ({record['set']} set) into {path.relative_to(ROOT)}")
        elif args.command == "label-second-look":
            record = json.loads(labeling.record_path(args.name).read_text())
            items = labeling.blind_set(dataset, record["set"])
            answers = {b: record["labels"][m] for b, m in record["blind_ids"].items()}
            rows = labeling.disagreements(items, answers, dataset)
            page = labeling.WORK_DIR / f"second-look-{args.name}.html"
            page.write_text(labeling.second_page(rows), encoding="utf-8")
            print(f"open {page} in a browser: {len(rows)} disagreements")
        else:
            saved = json.loads(args.file.read_text())
            out = {"saved_at": saved.get("saved_at"), "answers": saved["answers"]}
            path = labeling.second_look_path(args.name)
            path.write_text(json.dumps(out, indent=2) + "\n")
            print(f"imported {len(out['answers'])} decisions into {path.relative_to(ROOT)}")
        return
    if args.command == "report":
        run_dir = args.run_dir or latest_run()
        full, public = write_reports(run_dir)
        print(f"full edition (local only): {full.relative_to(ROOT)}\npublic edition: {public.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
