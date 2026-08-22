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
