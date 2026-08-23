from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_presets_endpoint():
    response = client.get("/api/presets")
    assert response.status_code == 200
    presets = response.json()
    assert len(presets) >= 5
    assert any(p["Mfg_Part_Num"] == "PDSH4816AF" for p in presets)


def test_taxonomy_endpoint():
    response = client.get("/api/taxonomy")
    assert response.status_code == 200
    data = response.json()
    assert data["template_count"] >= 10


def test_batch_segment_filters_by_template():
    from app.main import _filter_rows
    from ingest.csv_io import read_input_rows
    from app.config import DEFAULT_INPUT

    rows = read_input_rows(DEFAULT_INPUT)
    dishwashers = _filter_rows(rows, "built_in_dishwasher")
    fans = _filter_rows(rows, "ceiling_fan")
    assert dishwashers
    assert all("dishwasher" in r["Part_Desc"].lower() for r in dishwashers)
    assert fans
    assert not any("dishwasher" in r["Part_Desc"].lower() for r in fans)
    assert _filter_rows(rows, "dishwasher") == dishwashers


def test_enrich_single_endpoint():
    payload = {
        "Mfg_Part_Num": "49-94-3000",
        "Part_Desc": '3" x 0.040" x 3/8" Metal Cut Off Wheel',
        "DIB_Brand": "MILWAUKEE",
    }
    response = client.post("/api/enrich/single", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["mpn"] == "49-94-3000"
    assert data["category_id"] == "metal_cutoff_disc"
    assert "preview" in data
    assert len(data["preview"]["specs"]) >= 1
    assert "descriptions_list" in data["preview"]


def test_downloads_endpoints():
    csv_resp = client.get("/download/csv")
    assert csv_resp.status_code == 200
    assert "text/csv" in csv_resp.headers.get("content-type", "")

    prov_resp = client.get("/download/provenance")
    assert prov_resp.status_code == 200
    assert "application/json" in prov_resp.headers.get("content-type", "")


def test_enrich_parse_does_not_enrich():
    csv_text = 'Mfg_Part_Num,Part_Desc,E1_Brand,Unilog_Brand,DIB_Brand,Part_Manuf\n"X,1","Widget, SS",,-- No Unilog Brand --,Acme,Acme Corp\n'
    response = client.post(
        "/api/enrich/parse",
        files={"file": ("parts.csv", csv_text, "text/csv")},
        data={"limit": "0"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["rows"][0]["Mfg_Part_Num"] == "X,1"
    assert data["rows"][0]["Part_Desc"] == "Widget, SS"
    assert "Classpath" not in data["rows"][0]
    assert "summary" not in data


def test_enrich_post_is_parse_only():
    csv_text = "Mfg_Part_Num,Part_Desc,E1_Brand,Unilog_Brand,DIB_Brand,Part_Manuf\nX1,Widget SS,,-- No Unilog Brand --,Acme,Acme Corp\n"
    response = client.post(
        "/enrich",
        files={"file": ("parts.csv", csv_text, "text/csv")},
        data={"limit": "0"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["rows"][0]["Mfg_Part_Num"] == "X1"
    assert "summary" not in data
    assert "Classpath" not in data["rows"][0]


def test_enrich_window_returns_url_memory():
    response = client.post(
        "/api/enrich/window",
        json={
            "offset": 0,
            "total": 1,
            "rows": [
                {
                    "Mfg_Part_Num": "49-94-3000",
                    "Part_Desc": '3" x 0.040" x 3/8" Metal Cut Off Wheel',
                    "DIB_Brand": "MILWAUKEE",
                }
            ],
        },
    )
    assert response.status_code == 200
    assert '"url_memory"' in response.text


def test_url_memory_restore_keeps_learned_product_url():
    from sources.known_urls import known_urls_for, remember_urls, _reset_cache
    from sources.url_store import restore, snapshot

    remember_urls("LEARNED-1", ["https://www.milwaukeetool.com/en-us/LEARNED-1"])
    memory = snapshot()
    assert "LEARNED-1" in memory["known_urls"]
    restore({"known_urls": {}, "search_paths": memory["search_paths"], "dead_paths": {}, "learned_hosts": {"storefront": []}})
    assert known_urls_for("LEARNED-1") == []
    restore(memory)
    assert known_urls_for("LEARNED-1")[0].endswith("/LEARNED-1")
    _reset_cache()


def test_enrich_window_processes_one_uploaded_row():
    response = client.post(
        "/api/enrich/window",
        json={
            "offset": 0,
            "total": 1,
            "rows": [
                {
                    "Mfg_Part_Num": "49-94-3000",
                    "Part_Desc": '3" x 0.040" x 3/8" Metal Cut Off Wheel',
                    "DIB_Brand": "MILWAUKEE",
                }
            ],
        },
    )
    assert response.status_code == 200
    assert '"type": "complete"' in response.text
    assert "49-94-3000" in response.text
    assert '"done": true' in response.text


def test_enrich_stream_window_then_commit():
    first = client.get("/api/enrich/stream", params={"limit": 2, "offset": 0, "window": 1, "save": 0})
    assert first.status_code == 200
    assert '"type": "start"' in first.text
    assert '"total": 2' in first.text
    assert '"headers"' in first.text
    second = client.get("/api/enrich/stream", params={"limit": 2, "offset": 1, "window": 1, "save": 0})
    assert second.status_code == 200
    assert '"done": true' in second.text
    commit = client.post(
        "/api/enrich/commit",
        json={"filter": "", "summary": {"rows": 2}, "rows": [], "previews": [], "delivery": []},
    )
    assert commit.status_code == 200
    assert commit.json() == {"ok": True, "rows": 0}


def test_catalog_contribute_attribute_and_flag(tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.OUTPUT_DIR", tmp_path)
    monkeypatch.setattr("app.main.LAST_REPORT_PATH", tmp_path / "last_report.json")
    preview = {
        "mpn": "ZZ-API-1",
        "category_id": "generic_industrial",
        "input": {
            "Mfg_Part_Num": "ZZ-API-1",
            "Part_Desc": "Brass bushing",
            "E1_Brand": "",
            "Unilog_Brand": "",
            "DIB_Brand": "",
            "Part_Manuf": "Acme",
        },
        "specs": [
            {
                "slot": 2,
                "label": "Size",
                "value": "1440",
                "uom": "",
                "display": "1440",
                "source": "https://www.newdealer.example/p/ZZ-API-1",
            }
        ],
        "identity": {"BRAND_NAME": "Acme"},
        "taxonomy": {},
        "evidence_count": 1,
    }
    added = client.post(
        "/api/catalog/contribute",
        json={
            "mpn": "ZZ-API-1",
            "preview": preview,
            "input": preview["input"],
            "category_id": "generic_industrial",
            "attributes": [{"label": "Material", "value": "Brass"}],
        },
    )
    assert added.status_code == 200
    body = added.json()
    assert body["preview"]["mpn"] == "ZZ-API-1"
    labels = [item["label"] for item in body["preview"]["specs"]]
    assert "Material" in labels
    flagged = client.post(
        "/api/catalog/contribute",
        json={
            "mpn": "ZZ-API-1",
            "preview": body["preview"],
            "input": preview["input"],
            "category_id": "generic_industrial",
            "flags": [{"label": "Size", "value": "1440", "reason": "OG image width", "source": "https://www.newdealer.example/p/ZZ-API-1"}],
        },
    )
    assert flagged.status_code == 200
    specs = flagged.json()["preview"]["specs"]
    assert all(item.get("value") != "1440" for item in specs)
    assert flagged.json()["url_memory"]["reviewer"]["rejected"]
