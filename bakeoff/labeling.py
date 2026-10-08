"""Blind human labeling, for anyone who clones the repository (spec 007).

A labeler picks a message set, answers plain questions with no definitions and no
labels on a local page, then reviews each disagreement with the definition shown.
Nothing the first page carries names a message, a label as an answer, or a
definition. Each labeling is kept under the labeler's chosen name.
"""

import html
import json
import random
import re
from datetime import datetime, timezone
from pathlib import Path

from .dataset import ROOT
from .questions import BY_NAME, QUESTIONS

HUMAN_DIR = ROOT / "data" / "human"
EXCLUDED_FILE = HUMAN_DIR / "unseen-excluded.json"
WORK_DIR = ROOT / "results" / "labeling"  # local only: the pages before anything is committed
SETS = ("edits", "unseen")
SEEDS = {"edits": 11, "unseen": 7}
UNSEEN_SIZE = 60
EXPOSURE = {
    "none": "Nothing about this project",
    "report": "The published report",
    "specs-or-code": "The specs or code",
    "review": "The review discussions themselves",
}

# B2: plain questions with the definitions removed (spec 007 Assumptions).
PLAIN = {
    "intent": "What does the sender want?",
    "timeline": "When does the sender plan to act?",
    "wants_contact": "Does the sender ask to be contacted?",
    "urgency": "How urgent is the request?",
}


def excluded(path: Path | None = None) -> set[str]:
    rec = json.loads((path or EXCLUDED_FILE).read_text())
    shown = rec["shown_in_review"]
    return set(rec["edited"]) | set(shown["reviewer_count"]) | set(shown["quoted_in_replies"])


def message_ids(set_name: str, dataset: list[dict]) -> list[str]:
    """B1: the edits set is spec 004's 72 messages; the unseen set is a fixed draw of 60."""
    if set_name == "edits":
        from . import relabel

        return sorted(i["message_id"] for i in relabel.blind_set(dataset, relabel.edited_labels()))
    if set_name == "unseen":
        skip = excluded()
        pool = sorted(m["id"] for m in dataset if m["id"] not in skip)
        return sorted(random.Random(SEEDS["unseen"]).sample(pool, UNSEEN_SIZE))
    raise ValueError(f"unknown set {set_name!r}; choose one of {SETS}")


def blind_set(dataset: list[dict], set_name: str = "unseen") -> list[dict]:
    """The chosen set in its own shuffled order, under opaque ids; message ids stay off the page."""
    chosen = message_ids(set_name, dataset)
    random.Random(SEEDS[set_name] * 101).shuffle(chosen)
    text = {m["id"]: m["text"] for m in dataset}
    return [{"blind_id": f"q{i + 1:02d}", "message_id": mid, "text": text[mid]} for i, mid in enumerate(chosen)]


def record_path(name: str) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,39}", name):
        raise ValueError("a labeler name is 1 to 40 lowercase letters, digits or hyphens")
    return HUMAN_DIR / f"{name}.json"


def second_look_path(name: str) -> Path:
    return record_path(name).with_name(f"{name}-second-look.json")


_CSS = """
:root{--bg:#fff;--fg:#1d1d1f;--muted:#6b6b70;--line:#d9d9de;--card:#f6f6f8;--accent:#2b59c3;--on:#fff}
@media (prefers-color-scheme:dark){:root{--bg:#141416;--fg:#ececee;--muted:#a0a0a8;--line:#34343a;--card:#1d1d21;--accent:#7aa2ff;--on:#0b0b0d}}
*{box-sizing:border-box}body{background:var(--bg);color:var(--fg);font:16px/1.5 -apple-system,system-ui,sans-serif;margin:0 auto;max-width:760px;padding:20px 16px 60px}
h1{font-size:20px;margin:0 0 4px}.muted{color:var(--muted)}.msg{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;margin:16px 0;white-space:pre-wrap}
fieldset{border:0;margin:0 0 14px;padding:0}legend{font-weight:600;margin-bottom:6px}.opts{display:flex;flex-wrap:wrap;gap:8px}
.opts label{border:1px solid var(--line);border-radius:999px;padding:6px 12px;cursor:pointer;user-select:none}
.opts input{position:absolute;opacity:0}.opts input:checked+span{color:var(--on)}.opts label:has(input:checked){background:var(--accent);border-color:var(--accent);color:var(--on)}
.opts label:has(input:focus-visible){outline:2px solid var(--accent);outline-offset:2px}
.bar{height:6px;background:var(--line);border-radius:3px;overflow:hidden;margin:10px 0}.bar i{display:block;height:100%;background:var(--accent)}
.nav{display:flex;gap:10px;flex-wrap:wrap;margin-top:18px}button{font:inherit;padding:8px 16px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--fg);cursor:pointer}
button.primary{background:var(--accent);border-color:var(--accent);color:var(--on)}button:disabled{opacity:.45;cursor:default}.def{font-size:14px;border-left:3px solid var(--accent);padding:6px 10px;margin:8px 0}
"""


def _page(title: str, intro: str, data: dict, script: str) -> str:
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{html.escape(title)}</title><style>{_CSS}</style></head><body>"
        f"<h1>{html.escape(title)}</h1><p class='muted'>{intro}</p><div id='app'></div>"
        f"<script>const DATA = {json.dumps(data, ensure_ascii=False)};\n{script}</script></body></html>"
    )


# One script for both pages: progress in localStorage (B3), a file download at the end,
# and no network request of any kind.
_SCRIPT = r"""
const KEY = DATA.storageKey;
let state = {};
try { state = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) { state = {}; }
state.answers = state.answers || {};
let idx = Math.min(state.idx || 0, DATA.items.length);
const app = document.getElementById("app");
function save(){ state.idx = idx; try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {} }
function esc(s){ const d = document.createElement("div"); d.textContent = s; return d.innerHTML; }
function complete(it){ const a = state.answers[it.id] || {}; return DATA.fields(it).every(f => (a[f.name] || []).length > 0); }
function render(){
  if (DATA.askExposure && !state.exposure) {
    let h = `<p><b>Before you start:</b> what had you already read about this project? Answer honestly; it is saved with your labels and shown beside them.</p><fieldset><div class="opts">`;
    for (const [k, v] of Object.entries(DATA.exposureOptions)) h += `<label><input type="radio" name="exposure" value="${k}"><span>${esc(v)}</span></label>`;
    app.innerHTML = h + `</div></fieldset><div class="nav"><button class="primary" id="go" disabled>Start</button></div>`;
    app.querySelectorAll('input[name="exposure"]').forEach(i => i.onchange = () => { document.getElementById("go").disabled = false; });
    document.getElementById("go").onclick = () => { state.exposure = app.querySelector('input[name="exposure"]:checked').value; save(); render(); };
    return;
  }
  const done = DATA.items.filter(complete).length;
  if (idx >= DATA.items.length) {
    app.innerHTML = `<div class="bar"><i style="width:100%"></i></div><p>${done} of ${DATA.items.length} answered.</p>` +
      `<div class="nav"><button id="back">Back</button><button class="primary" id="dl" ${done < DATA.items.length ? "disabled" : ""}>Save answers to a file</button></div>` +
      (done < DATA.items.length ? `<p class="muted">Answer every item before saving. Use Back to find the gaps.</p>` : "");
    document.getElementById("back").onclick = () => { idx = DATA.items.length - 1; save(); render(); };
    const dl = document.getElementById("dl");
    if (dl && !dl.disabled) dl.onclick = () => {
      const out = { kind: DATA.kind, set: DATA.set, exposure: state.exposure || null, saved_at: new Date().toISOString(), answers: state.answers };
      const url = URL.createObjectURL(new Blob([JSON.stringify(out, null, 2)], { type: "application/json" }));
      const a = document.createElement("a"); a.href = url; a.download = DATA.fileName; a.click(); URL.revokeObjectURL(url);
    };
    return;
  }
  const it = DATA.items[idx], a = state.answers[it.id] || {};
  let h = `<div class="bar"><i style="width:${100 * done / DATA.items.length}%"></i></div>` +
          `<p class="muted">Item ${idx + 1} of ${DATA.items.length} · ${done} answered</p>${DATA.header(it)}`;
  for (const f of DATA.fields(it)) {
    h += `<fieldset><legend>${esc(f.label)}${f.max > 1 ? ' <span class="muted">(one, or two if it clearly asks for two things)</span>' : ""}</legend>${f.note || ""}<div class="opts">`;
    for (const o of f.options) {
      const on = (a[f.name] || []).includes(o.value);
      h += `<label><input type="${f.max > 1 ? "checkbox" : "radio"}" name="${f.name}" value="${esc(o.value)}" ${on ? "checked" : ""}><span>${esc(o.text)}</span></label>`;
    }
    h += `</div></fieldset>`;
  }
  h += `<div class="nav"><button id="prev" ${idx === 0 ? "disabled" : ""}>Back</button><button class="primary" id="next">Next</button></div>`;
  app.innerHTML = h;
  for (const f of DATA.fields(it)) {
    app.querySelectorAll(`input[name="${f.name}"]`).forEach(inp => inp.onchange = () => {
      let cur = Array.from(app.querySelectorAll(`input[name="${f.name}"]:checked`)).map(x => x.value);
      if (cur.length > f.max) { inp.checked = false; cur = cur.filter(v => v !== inp.value); }
      state.answers[it.id] = Object.assign({}, state.answers[it.id], { [f.name]: cur }); save();
    });
  }
  document.getElementById("prev").onclick = () => { idx--; save(); render(); };
  document.getElementById("next").onclick = () => { idx++; save(); render(); };
}
render();
"""


def first_page(items: list[dict], set_name: str) -> str:
    """B2/B3/B4: message text and plain questions only, after asking what the labeler had read."""
    fields = [
        {"name": q.name, "label": PLAIN[q.name], "max": 2 if q.name == "intent" else 1,
         "options": [{"value": l, "text": l} for l in q.labels]}
        for q in QUESTIONS
    ]
    data = {"kind": "first-pass", "set": set_name, "storageKey": f"bakeoff-labeling-{set_name}", "fileName": f"labels-{set_name}.json",
            "askExposure": True, "exposureOptions": EXPOSURE,
            "items": [{"id": i["blind_id"], "text": i["text"]} for i in items], "fieldList": fields}
    script = "DATA.fields = () => DATA.fieldList;\nDATA.header = it => `<div class=\"msg\">${esc(it.text)}</div>`;\n" + _SCRIPT
    intro = (f"Read each of the {len(items)} messages and answer the four questions the way you would triage it yourself. "
             "There are no right answers and no definitions on purpose. Your progress is saved in this browser.")
    return _page(f"Label {len(items)} lead messages", intro, data, script)


def matches(answer: list[str], labels: list[str]) -> bool:
    """An answer matches when it shares a label with the label set (either intent counts)."""
    return bool(set(answer) & set(labels))


def disagreements(items: list[dict], answers: dict, dataset: list[dict]) -> list[dict]:
    truth = {m["id"]: m["truth"] for m in dataset}
    out = []
    for it in items:
        a = answers.get(it["blind_id"], {})
        for q in QUESTIONS:
            mine, frozen = a.get(q.name, []), truth[it["message_id"]][q.name]
            if mine and not matches(mine, frozen):
                out.append({"id": f"{it['blind_id']}-{q.name}", "blind_id": it["blind_id"], "question": q.name,
                            "text": it["text"], "mine": mine, "frozen": frozen})
    return out


def second_page(rows: list[dict]) -> str:
    """B5: each disagreement with the definition and the frozen label shown."""
    items = [{"id": r["id"], "text": r["text"], "q": r["question"], "mine": r["mine"], "frozen": r["frozen"],
              "definition": BY_NAME[r["question"]].text} for r in rows]
    data = {"kind": "second-look", "set": None, "storageKey": "bakeoff-labeling-second-look", "fileName": "second-look.json",
            "askExposure": False, "items": items}
    script = (
        "DATA.fields = it => [{name: 'decision', label: 'After reading the definition, which answer do you keep?', max: 1, "
        "note: `<div class=\"def\">${esc(it.definition)}</div><p>Yours: <b>${esc(it.mine.join(' / '))}</b> · "
        "Frozen label: <b>${esc(it.frozen.join(' / '))}</b></p>`, "
        "options: [{value: 'keep mine', text: 'Keep mine'}, {value: 'keep frozen', text: 'Keep the frozen label'}, {value: 'unsure', text: 'Unsure'}]}];\n"
        "DATA.header = it => `<p class=\"muted\">Question: ${esc(it.q)}</p><div class=\"msg\">${esc(it.text)}</div>`;\n" + _SCRIPT
    )
    intro = ("These are the answers where you differed from the frozen label. Each shows the definition the models "
             "were given. Your first answers are kept as they were; this only records which you would keep now.")
    return _page(f"Second look: {len(items)} disagreements", intro, data, script)


def import_first(dataset: list[dict], saved: dict, name: str) -> dict:
    """Map the page's opaque ids back to messages, validate every answer, keep the declaration."""
    set_name = saved.get("set")
    if set_name not in SETS:
        raise ValueError("the saved file names no known message set")
    if saved.get("exposure") not in EXPOSURE:
        raise ValueError("the saved file has no answer to what the labeler had read")
    items = blind_set(dataset, set_name)
    ans = saved["answers"]
    labels = {}
    for it in items:
        a = ans.get(it["blind_id"]) or {}
        row = {}
        for q in QUESTIONS:
            vals = [v for v in a.get(q.name, []) if v in q.labels]
            if not vals or len(vals) > (2 if q.name == "intent" else 1):
                raise ValueError(f"{it['blind_id']} {q.name}: missing or invalid answer")
            row[q.name] = vals
        labels[it["message_id"]] = row
    return {"labeler": name, "set": set_name, "seed": SEEDS[set_name], "exposure": saved["exposure"],
            "plain_questions": PLAIN, "saved_at": saved.get("saved_at"),
            "imported_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "labels": labels,
            "blind_ids": {it["blind_id"]: it["message_id"] for it in items}}


def load_all() -> list[dict]:
    """Every labeling on record, each with its second look when there is one."""
    out = []
    for p in sorted(HUMAN_DIR.glob("*.json")):
        if p.name == EXCLUDED_FILE.name or p.name.endswith("-second-look.json"):
            continue
        rec = json.loads(p.read_text())
        sl = second_look_path(rec["labeler"])
        rec["second_look"] = json.loads(sl.read_text()) if sl.exists() else None
        out.append(rec)
    return out


def with_labels(dataset: list[dict], record: dict, edits: dict | None = None) -> list[dict]:
    """B7: on the edits set, the labeler's answer replaces each edited label only; on the
    unseen set, the labeler's labels replace the frozen ones on its messages."""
    import copy

    out = copy.deepcopy(dataset)
    by_id = {m["id"]: m for m in out}
    if record["set"] == "edits":
        for (mid, q), _ in (edits or {}).items():
            if mid in record["labels"]:
                by_id[mid]["truth"][q] = list(record["labels"][mid][q])
    else:
        for mid, row in record["labels"].items():
            by_id[mid]["truth"] = {q: list(v) for q, v in row.items()}
    return out


def second_look_counts(record: dict) -> dict[str, dict[str, int]]:
    out = {q.name: {"keep mine": 0, "keep frozen": 0, "unsure": 0} for q in QUESTIONS}
    for key, a in record["answers"].items():
        q = key.split("-", 1)[1]
        out[q][a["decision"][0]] += 1
    return out


def edits_agreement(record: dict, dataset: list[dict], edits: dict) -> dict:
    """B5 on the edits set: per question, over edited labels, whether the labeler's answer
    shares a label with the frozen or the generated version, and the control baseline."""
    truth = {m["id"]: m["truth"] for m in dataset}
    edited_ids = {mid for mid, _ in edits}
    out = {}
    for q in QUESTIONS:
        row = {"edited": 0, "frozen": 0, "generated": 0, "neither": 0, "control": 0, "control_agree": 0}
        for (mid, qn), (old, new) in edits.items():
            if qn != q.name or mid not in record["labels"]:
                continue
            ans = record["labels"][mid][q.name]
            row["edited"] += 1
            if matches(ans, new):
                row["frozen"] += 1
            elif matches(ans, old):
                row["generated"] += 1
            else:
                row["neither"] += 1
        for mid, ans in record["labels"].items():
            if mid not in edited_ids:
                row["control"] += 1
                row["control_agree"] += matches(ans[q.name], truth[mid][q.name])
        out[q.name] = row
    return out
