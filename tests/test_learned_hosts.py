"""A new SKU can teach later SKUs: junk-only dealer hosts are remembered."""

from extract.evidence import Evidence, EvidenceBundle
from sources.domain_discovery import discover_domains_from_urls
from sources.finder import is_blocked_url
from sources.learned_hosts import (
    apply_run_lessons,
    is_learned_storefront,
    learn_from_page,
    note_storefront_host,
    storefront_hosts,
)
from sources.url_patterns import promote_templates
from sources.url_store import restore, snapshot


DEALER = "https://www.newdealer.example/catalog/p/ZZ-NEW-SKU"
OEM = "https://www.acmetoolsbrand.com/p/ZZ-NEW-SKU"
MAGENTO_HTML = """
<html><body>
  <script type="application/ld+json">
  {"@type":"LocalBusiness","name":"New Dealer","address":{"@type":"PostalAddress",
    "addressLocality":"Springfield"}}
  </script>
  <dt>town_name</dt><dd>Springfield</dd>
  <dt>Size</dt><dd>1440</dd>
  <dt>Color</dt><dd>#444</dd>
</body></html>
"""


def _junk_bundle(url: str) -> EvidenceBundle:
    bundle = EvidenceBundle(mfr_url=url)
    bundle.set(Evidence(field="Size", value="1440", source_url=url, extractor="html", confidence=0.8))
    bundle.set(Evidence(field="Color", value="#444", source_url=url, extractor="html", confidence=0.8))
    bundle.set(Evidence(field="town_name", value="Springfield", source_url=url, extractor="html", confidence=0.4))
    return bundle


def test_junk_storefront_host_is_blocked_for_later_skus():
    later = "https://www.newdealer.example/catalog/p/ZZ-NEXT"
    assert not is_blocked_url(DEALER)
    assert not is_blocked_url(later)
    learned = learn_from_page(DEALER, MAGENTO_HTML, _junk_bundle(DEALER), names=["Acme Tools Brand"])
    assert learned
    assert is_learned_storefront(later)
    assert is_blocked_url(later)
    assert "newdealer.example" in storefront_hosts()
    assert not is_blocked_url(OEM)


def test_oem_with_real_specs_is_not_learned_as_storefront():
    bundle = EvidenceBundle(mfr_url=OEM)
    bundle.set(Evidence(field="Voltage Rating", value="120", uom="V", source_url=OEM, extractor="html", confidence=0.9))
    bundle.set(Evidence(field="Size", value="1440", source_url=OEM, extractor="html", confidence=0.4))
    html = MAGENTO_HTML.replace("New Dealer", "Acme")
    assert not learn_from_page(OEM, html, bundle, names=["Acme Tools Brand"])
    assert not is_blocked_url(OEM)


def test_name_matched_host_is_not_blocked_by_storefront_chrome():
    html = "<html><dt>town_name</dt><dd>Springfield</dd></html>"
    empty = EvidenceBundle(mfr_url=OEM)
    assert not learn_from_page(OEM, html, empty, names=["Acme Tools Brand"])
    assert not is_learned_storefront(OEM)


def test_distributor_host_is_not_learned_as_storefront():
    url = "https://www.grainger.com/product/ZZ-NEW-SKU"
    bundle = _junk_bundle(url)
    assert not learn_from_page(url, MAGENTO_HTML, bundle, names=["Acme Tools Brand"])
    assert not is_learned_storefront(url)


def test_current_sku_drops_storefront_evidence():
    bundle = _junk_bundle(DEALER)
    apply_run_lessons(bundle, names=["Acme Tools Brand"])
    assert bundle.mfr_url == ""
    assert bundle.items == []
    assert is_blocked_url("https://www.newdealer.example/catalog/p/OTHER")


def test_learned_host_is_not_adopted_as_manufacturer_domain():
    note_storefront_host(DEALER)
    domains = discover_domains_from_urls(
        [DEALER, OEM],
        mpn="ZZ-NEW-SKU",
        names=["Acme Tools Brand"],
    )
    assert "newdealer.example" not in domains
    assert "acmetoolsbrand.com" in domains


def test_storefront_url_is_not_promoted_to_host_templates():
    note_storefront_host(DEALER)
    added = promote_templates("ZZ-NEW-SKU", [DEALER])
    assert added == []


def test_url_memory_snapshot_keeps_learned_storefront():
    note_storefront_host(DEALER)
    memory = snapshot()
    assert "newdealer.example" in memory["learned_hosts"]["storefront"]
    restore({"known_urls": {}, "search_paths": memory["search_paths"], "dead_paths": {}, "learned_hosts": {"storefront": []}})
    assert not is_learned_storefront(DEALER)
    restore(memory)
    assert is_learned_storefront(DEALER)
