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
