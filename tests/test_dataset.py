from bakeoff import dataset as ds


def _candidate():
    return [{**s, "text": "Looking to buy soon. Reach me at 206-555-0142 or sam@example.com."} for s in ds.build_specs()]


def test_label_specs_cover_every_label():
    assert ds.check_dataset(_candidate()) == []


def test_b2_out_of_range_phone_is_rejected():
    rows = _candidate()
    rows[3]["text"] = "Call me at 206-555-0247 about selling."
    problems = ds.check_dataset(rows)
    assert any("206-555-0247" in p for p in problems)


def test_b2_non_example_email_is_rejected():
    rows = _candidate()
    rows[5]["text"] = "Email jane@gmail.com please."
    problems = ds.check_dataset(rows)
    assert any("jane@gmail.com" in p for p in problems)


def test_reserved_phone_formats_pass():
    for text in ("206-555-0142", "(206) 555-0199", "+1 206.555.0100", "2065550150"):
        assert ds.check_message(f"call {text}") == [], text


def test_real_looking_phone_fails():
    assert ds.check_message("call 206-867-5309")


def test_freeze_refuses_a_bad_candidate(tmp_path, monkeypatch):
    rows = _candidate()
    rows[0]["text"] = "jane@gmail.com"
    cand = tmp_path / "candidate.jsonl"
    ds.write_jsonl(cand, rows)
    monkeypatch.setattr(ds, "DATASET_FILE", tmp_path / "dataset.jsonl")
    monkeypatch.setattr(ds, "META_FILE", tmp_path / "dataset.meta.json")
    try:
        ds.freeze(cand)
    except ValueError:
        pass
    else:
        raise AssertionError("freeze accepted a candidate with a real email domain")
    assert not (tmp_path / "dataset.jsonl").exists()


def test_freeze_then_tamper_is_detected(tmp_path, monkeypatch):
    cand = tmp_path / "candidate.jsonl"
    ds.write_jsonl(cand, _candidate())
    monkeypatch.setattr(ds, "DATASET_FILE", tmp_path / "dataset.jsonl")
    monkeypatch.setattr(ds, "META_FILE", tmp_path / "dataset.meta.json")
    version = ds.freeze(cand)
    rows, loaded = ds.load_frozen()
    assert loaded == version and len(rows) == ds.SIZE
    (tmp_path / "dataset.jsonl").write_text((tmp_path / "dataset.jsonl").read_text().replace("buy", "rent", 1))
    try:
        ds.load_frozen()
    except ValueError:
        return
    raise AssertionError("an edited frozen dataset loaded without complaint")
