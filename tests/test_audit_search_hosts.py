"""Offline parsing tests for the search-host auditor."""

from scripts.audit_search_hosts import cite_to_url, result_urls, unwrap


def test_path_import_and_output_location():
    from pathlib import Path
    from scripts import audit_search_hosts

    assert audit_search_hosts.OUT.name == "search_host_audit.json"
    assert isinstance(audit_search_hosts.OUT, Path)


def test_unwrap_bing_ck_a_base64():
    href = (
        "https://www.bing.com/ck/a?!&&p=abc&u="
        "a1aHR0cHM6Ly93d3cuZnJpZ2lkYWlyZS5jb20vZW4vcC9QRFNINDgxNkFG"
    )
    assert unwrap(href) == "https://www.frigidaire.com/en/p/PDSH4816AF"


def test_cite_to_url_rebuilds_brave_breadcrumb():
    assert (
        cite_to_url("frigidaire.com › en  › p  › kitchen  › dishwashers  › PDSH4816AF")
        == "https://frigidaire.com/en/p/kitchen/dishwashers/PDSH4816AF"
    )


def test_result_urls_from_ddg_like_html():
    html = """
    <html><body>
      <a class="result__a" href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.frigidaire.com%2Fen%2Fp%2FPDSH4816AF">mfr</a>
      <a href="https://www.amazon.com/dp/PDSH4816AF">shop</a>
      <a href="https://html.duckduckgo.com/html/">engine</a>
    </body></html>
    """
    urls = result_urls(html)
    assert "https://www.frigidaire.com/en/p/PDSH4816AF" in urls
    assert all("amazon." not in url for url in urls)
    assert all("duckduckgo." not in url for url in urls)


def test_refuse_bulk_search_without_limit():
    from scripts.audit_search_hosts import refuse_bulk_search

    assert refuse_bulk_search(True, 0, False)
    assert refuse_bulk_search(True, 8, False) is None
    assert refuse_bulk_search(True, 0, True) is None
    assert refuse_bulk_search(False, 0, False) is None


def test_default_audit_reads_persisted_known_urls():
    from scripts.audit_search_hosts import rows_from_known_urls
    from sources.known_urls import remember_urls

    remember_urls("ZZ-AUDIT-1", ["https://www.frigidaire.com/p/ZZ-AUDIT-1"])
    rows = rows_from_known_urls(["ZZ-AUDIT-1", "MISSING"])
    by_mpn = {row["mpn"]: row for row in rows}
    assert by_mpn["ZZ-AUDIT-1"]["source"] == "known_urls"
    assert "frigidaire.com" in by_mpn["ZZ-AUDIT-1"]["hosts"][0]
    assert by_mpn["MISSING"]["hosts"] == []
