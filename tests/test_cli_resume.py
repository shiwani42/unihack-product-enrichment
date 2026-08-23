"""CLI resume/checkpoint and Vercel cache paths."""

from ingest.csv_io import append_output_row, existing_output_mpns, write_output_rows


def test_existing_output_mpns_and_append(tmp_path):
    headers = ["Mfg_Part_Num", "BRAND_NAME"]
    path = tmp_path / "out.csv"
    write_output_rows(path, headers, [{"Mfg_Part_Num": "A1", "BRAND_NAME": "Acme"}])
    append_output_row(path, headers, {"Mfg_Part_Num": "B2", "BRAND_NAME": "Beta"})
    assert existing_output_mpns(path) == {"A1", "B2"}


def test_enrich_resume_skips_done_mpns(tmp_path, monkeypatch):
    from pipeline import EnrichmentResult
    import cli as cli_mod

    headers = ["Mfg_Part_Num", "Part_Desc", "BRAND_NAME"]
    source = tmp_path / "in.csv"
    write_output_rows(
        source,
        headers,
        [
            {"Mfg_Part_Num": "KEEP", "Part_Desc": "done", "BRAND_NAME": ""},
            {"Mfg_Part_Num": "NEW", "Part_Desc": "todo", "BRAND_NAME": ""},
        ],
    )
    output = tmp_path / "out.csv"
    write_output_rows(output, headers, [{"Mfg_Part_Num": "KEEP", "Part_Desc": "done", "BRAND_NAME": "Old"}])

    seen = []

    def fake_enrich(row, hdrs):
        seen.append(row["Mfg_Part_Num"])
        out = {key: row.get(key, "") for key in hdrs}
        out["BRAND_NAME"] = "New"
        return EnrichmentResult(
            row=out,
            confidence_band="medium",
            evidence_count=0,
            issues=[],
            field_sources={},
            category_id="generic_industrial",
        )

    monkeypatch.setattr(cli_mod, "enrich_input_row", fake_enrich)
    monkeypatch.setattr(cli_mod, "load_output_headers", lambda: headers)
    args = type(
        "Args",
        (),
        {
            "input": str(source),
            "output": str(output),
            "limit": 0,
            "workers": 1,
            "resume": True,
            "checkpoint": False,
            "dedupe": False,
            "xlsx": False,
            "provenance": "",
            "fresh": False,
        },
    )()
    cli_mod.cmd_enrich(args)
    assert seen == ["NEW"]
    mpns = existing_output_mpns(output)
    assert mpns == {"KEEP", "NEW"}


def test_activate_on_vercel_writes_under_tmp(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    from sources.url_store import activate, runtime_dir

    activate()
    import sources.dead_paths as dead_paths
    import sources.finder as finder
    import sources.known_urls as known_urls

    root = str(runtime_dir())
    assert root.startswith("/tmp/unilog")
    assert str(known_urls.KNOWN_URLS_FILE).startswith(root)
    assert str(finder.SEARCH_PATHS_FILE).startswith(root)
    assert str(dead_paths.DEAD_PATHS_FILE).startswith(root)
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("UNILOG_RAW_CACHE_DIR", raising=False)
    monkeypatch.delenv("UNILOG_EVIDENCE_CACHE_DIR", raising=False)
    import importlib
    import app.config as config

    importlib.reload(config)
    assert str(config.RAW_CACHE_DIR).startswith("/tmp/unilog")
    assert str(config.EVIDENCE_CACHE_DIR).startswith("/tmp/unilog")
    monkeypatch.delenv("VERCEL", raising=False)
    importlib.reload(config)


def test_pending_rows_keeps_duplicate_mpn_occurrences(tmp_path):
    from ingest.csv_io import pending_input_rows, write_output_rows

    headers = ["Mfg_Part_Num", "Part_Desc"]
    source = [
        {"Mfg_Part_Num": "AVM6EV", "Part_Desc": "one"},
        {"Mfg_Part_Num": "AVM6EV", "Part_Desc": "two"},
        {"Mfg_Part_Num": "X1", "Part_Desc": "three"},
    ]
    output = tmp_path / "out.csv"
    write_output_rows(output, headers, [{"Mfg_Part_Num": "AVM6EV", "Part_Desc": "one"}])
    pending = pending_input_rows(source, output)
    assert [row["Part_Desc"] for row in pending] == ["two", "three"]


def test_sanitize_drops_binary_for_xlsx(tmp_path):
    from ingest.csv_io import sanitize_cell
    from ingest.export_io import write_output_xlsx

    headers = ["Mfg_Part_Num", "MARKETING_DESCRIPTION"]
    junk = "ok\x00\x04binary"
    assert sanitize_cell(junk) == ""
    path = tmp_path / "out.xlsx"
    write_output_xlsx(
        path,
        headers,
        [{"Mfg_Part_Num": "WMMS3330RZ", "MARKETING_DESCRIPTION": junk}],
    )
    assert path.exists() and path.stat().st_size > 0


def test_batch_resume_after_partial_checkpoint(tmp_path, monkeypatch):
    from pipeline import EnrichmentResult
    import cli as cli_mod

    headers = ["Mfg_Part_Num", "Part_Desc", "BRAND_NAME"]
    source = tmp_path / "in.csv"
    write_output_rows(
        source,
        headers,
        [
            {"Mfg_Part_Num": "KEEP", "Part_Desc": "done", "BRAND_NAME": ""},
            {"Mfg_Part_Num": "NEW", "Part_Desc": "todo", "BRAND_NAME": ""},
            {"Mfg_Part_Num": "LATER", "Part_Desc": "todo2", "BRAND_NAME": ""},
        ],
    )
    output = tmp_path / "out.csv"
    write_output_rows(output, headers, [{"Mfg_Part_Num": "KEEP", "Part_Desc": "done", "BRAND_NAME": "Old"}])
    seen = []

    def fake_enrich(row, hdrs):
        seen.append(row["Mfg_Part_Num"])
        out = {key: row.get(key, "") for key in hdrs}
        out["BRAND_NAME"] = "Live"
        return EnrichmentResult(
            row=out,
            confidence_band="medium",
            evidence_count=2,
            issues=[],
            field_sources={"BRAND_NAME": "https://mfr.example/p"},
            category_id="generic_industrial",
        )

    monkeypatch.setattr(cli_mod, "enrich_input_row", fake_enrich)
    monkeypatch.setattr(cli_mod, "load_output_headers", lambda: headers)
    args = type(
        "Args",
        (),
        {
            "input": str(source),
            "output": str(output),
            "report": str(tmp_path / "report.json"),
            "filter": "all",
            "limit": 0,
            "workers": 1,
            "resume": True,
            "checkpoint": True,
            "xlsx": True,
            "provenance": str(tmp_path / "prov.json"),
            "fresh": False,
        },
    )()
    cli_mod.cmd_batch(args)
    assert seen == ["NEW", "LATER"]
    rows = [row["Mfg_Part_Num"] for row in __import__("ingest.csv_io", fromlist=["read_input_rows"]).read_input_rows(output)]
    assert rows == ["KEEP", "NEW", "LATER"]
    import json

    report = json.loads((tmp_path / "report.json").read_text())
    assert report["summary"]["rows"] == 3
    assert (tmp_path / "out.xlsx").exists()
    provenance = json.loads((tmp_path / "prov.json").read_text())
    assert {item["mpn"] for item in provenance} == {"KEEP", "NEW", "LATER"}


def test_worker_exception_is_checkpointed_not_fatal(tmp_path, monkeypatch):
    from pipeline import EnrichmentResult
    import cli as cli_mod

    headers = ["Mfg_Part_Num", "Part_Desc", "BRAND_NAME"]
    source = tmp_path / "in.csv"
    write_output_rows(
        source,
        headers,
        [
            {"Mfg_Part_Num": "OK", "Part_Desc": "ok", "BRAND_NAME": ""},
            {"Mfg_Part_Num": "BOOM", "Part_Desc": "bad", "BRAND_NAME": ""},
        ],
    )
    output = tmp_path / "out.csv"

    def fake_enrich(row, hdrs):
        if row["Mfg_Part_Num"] == "BOOM":
            raise RuntimeError("manufacturer site timed out")
        out = {key: row.get(key, "") for key in hdrs}
        out["BRAND_NAME"] = "Live"
        return EnrichmentResult(
            row=out,
            confidence_band="high",
            evidence_count=3,
            issues=[],
            field_sources={},
            category_id="generic_industrial",
        )

    monkeypatch.setattr(cli_mod, "enrich_input_row", fake_enrich)
    monkeypatch.setattr(cli_mod, "load_output_headers", lambda: headers)
    args = type(
        "Args",
        (),
        {
            "input": str(source),
            "output": str(output),
            "report": str(tmp_path / "report.json"),
            "filter": "all",
            "limit": 0,
            "workers": 2,
            "resume": True,
            "checkpoint": True,
            "xlsx": False,
            "provenance": "",
            "fresh": False,
        },
    )()
    cli_mod.cmd_batch(args)
    from ingest.csv_io import read_input_rows

    mpns = {row["Mfg_Part_Num"] for row in read_input_rows(output)}
    assert mpns == {"OK", "BOOM"}


def test_new_csv_does_not_append_to_foreign_output(tmp_path, monkeypatch):
    from pipeline import EnrichmentResult
    import cli as cli_mod
    from ingest.batch_run import write_meta, run_meta

    headers = ["Mfg_Part_Num", "Part_Desc", "BRAND_NAME"]
    old_in = tmp_path / "old.csv"
    new_in = tmp_path / "new.csv"
    write_output_rows(old_in, headers, [{"Mfg_Part_Num": "OLD", "Part_Desc": "old", "BRAND_NAME": ""}])
    write_output_rows(new_in, headers, [{"Mfg_Part_Num": "NEW", "Part_Desc": "new", "BRAND_NAME": ""}])
    output = tmp_path / "out.csv"
    write_output_rows(output, headers, [{"Mfg_Part_Num": "OLD", "Part_Desc": "old", "BRAND_NAME": "Kept"}])
    write_meta(output, run_meta(old_in, "all", 0, 1))

    def fake_enrich(row, hdrs):
        out = {key: row.get(key, "") for key in hdrs}
        out["BRAND_NAME"] = "Live"
        return EnrichmentResult(
            row=out,
            confidence_band="medium",
            evidence_count=1,
            issues=[],
            field_sources={},
            category_id="generic_industrial",
        )

    monkeypatch.setattr(cli_mod, "enrich_input_row", fake_enrich)
    monkeypatch.setattr(cli_mod, "load_output_headers", lambda: headers)
    args = type(
        "Args",
        (),
        {
            "input": str(new_in),
            "output": str(output),
            "report": str(tmp_path / "report.json"),
            "filter": "all",
            "limit": 0,
            "workers": 1,
            "resume": True,
            "checkpoint": True,
            "xlsx": False,
            "provenance": "",
            "fresh": False,
        },
    )()
    cli_mod.cmd_batch(args)
    from ingest.csv_io import read_input_rows

    assert [row["Mfg_Part_Num"] for row in read_input_rows(output)] == ["OLD"]
    siblings = list(tmp_path.glob("out-*.csv"))
    assert siblings
    assert [row["Mfg_Part_Num"] for row in read_input_rows(siblings[0])] == ["NEW"]
