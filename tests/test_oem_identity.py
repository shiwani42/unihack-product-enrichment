from identity.brand_resolver import resolve_identity


def test_police_security_uses_official_host():
    ident = resolve_identity(
        "97708",
        "97708 Police 800L Headlight",
        "-- Unbranded --",
        "Police Security",
        "Police Security (9470)",
    )
    assert ident.brand_key == "Police Security"
    assert ident.domains == ["policesecurity.com"]


def test_acg_brands_flashlight_is_nebo():
    ident = resolve_identity(
        "NEB-FLT-1021",
        "NEBFLT1021 Slyde King FlashLt",
        "-- Unbranded --",
        "-- No DIB Brand --",
        "ACG Brands (1154)",
    )
    assert ident.brand_key == "NEBO"
    assert ident.manufacturer_name == "ACG Brands"
    assert ident.domains == ["nebo.acgbrands.com"]


def test_tech_gear_heated_gloves_are_fieldsheer():
    ident = resolve_identity(
        "MWUG42010124",
        "UTW Pro Heated Glove Blk XS",
        "-- Unbranded --",
        "-- No DIB Brand --",
        "Tech Gear 5.7 Inc (TECGE)",
    )
    assert ident.brand_key == "Fieldsheer"
    assert ident.brand_name == "Mobile Warming"
    assert ident.domains == ["fieldsheer.com"]


def test_ohio_firewatch_extinguisher_is_efirex():
    ident = resolve_identity(
        "FE-EFX-6L",
        "FEEFX6L Lith Fire Extinguisher",
        "-- Unbranded --",
        "-- No DIB Brand --",
        "Ohio Firewatch Protection Inc (HOLFS)",
    )
    assert ident.brand_key == "eFireX"
    assert ident.domains == ["efirex.com"]


def test_fenton_cord_grip_is_amfico_without_stealing_lutron():
    grip = resolve_identity(
        "CG50K",
        'CG50K 1/2" Cord Grip Kit',
        "-- Unbranded --",
        "-- No DIB Brand --",
        "Fenton Bros Electric Inc (FENBR)",
    )
    assert grip.brand_key == "American Fittings"
    assert grip.domains == ["amftgs.com"]

    lutron = resolve_identity(
        "AYCL-153PH-LA",
        "AYCL-153PH-LA Lutron Dimmer LA",
        "-- Unbranded --",
        "-- No DIB Brand --",
        "Fenton Bros Electric Inc (FENBR)",
    )
    assert lutron.brand_key == "Lutron"
    assert "lutron.com" in lutron.domains


def test_steff_feeder_is_maggi_not_jg_machinery():
    ident = resolve_identity(
        "MAG:2044-230-1",
        "2044-230-1 Stock Feeder 4-Roll - Steff",
        "-- Unbranded --",
        "-- No DIB Brand --",
        "J&G Machinery (JGMAC)",
    )
    assert ident.brand_key == "Maggi"
    assert ident.brand_name == "Steff"
    assert ident.domains == ["maggi-technology.com"]


def test_vv_heater_kit_is_speed_queen():
    ident = resolve_identity(
        "D519127",
        "D519127 Heater Kit",
        "-- Unbranded --",
        "-- No DIB Brand --",
        "V & V Appliance Parts Inc (VVAPP)",
    )
    assert ident.brand_key == "Speed Queen"
    assert "speedqueen.com" in ident.domains


def test_century_mason_line_is_us_tape():
    ident = resolve_identity(
        "25168",
        "25168 Mason Line Brd Green - 250'",
        "CENTURY COMPONENTS",
        "-- No DIB Brand --",
        "U S Tape Company (6694)",
    )
    assert ident.brand_key == "US Tape"
    assert ident.domains == ["ustape.com"]


def test_palmer_donavin_rows_resolve_from_product_not_wholesaler():
    shingles = resolve_identity(
        "1504345",
        "OC Duration TruDef Wburg Gray (BDL)",
        "-- Unbranded --",
        "-- No DIB Brand --",
        "Palmer Donavin Mfg Company (PALDO)",
    )
    assert shingles.brand_key == "Owens Corning"
    assert shingles.domains == ["owenscorning.com"]

    ice = resolve_identity(
        "2733",
        "3'x65' Henry Eaveguard - Ice Guard",
        "-- Unbranded --",
        "-- No DIB Brand --",
        "Palmer Donavin Mfg Company (PALDO)",
    )
    assert ice.brand_key == "Henry"
    assert ice.domains == ["henry.com"]

    tile = resolve_identity(
        "1728ABL",
        "2x2 Black Fine Fissured 1728BL",
        "-- Unbranded --",
        "-- No DIB Brand --",
        "Palmer Donavin Mfg Company (PALDO)",
    )
    assert tile.brand_key == "Armstrong Ceilings"
    assert tile.domains == ["armstrongceilings.com"]

    wrap = resolve_identity(
        "173950TBK",
        '4"x8\'-6" DSI SQ Black Alum Post Wrap',
        "-- Unbranded --",
        "-- No DIB Brand --",
        "Palmer Donavin Mfg Company (PALDO)",
    )
    assert wrap.brand_key == "Westbury"
    assert wrap.domains == ["diggerspecialties.com"]


def test_sq_elect_dryer_still_speed_queen():
    ident = resolve_identity(
        "DR7004BE",
        "DR7004BE SQ Elect Dryer Bk",
        "-- Unbranded --",
        "-- No DIB Brand --",
        "Appliance Dealers Cooperative (APPDE)",
    )
    assert ident.brand_key == "Speed Queen"
    assert "speedqueen.com" in ident.domains


def test_desc_named_oems_resolve_without_dealer_part_manuf():
    washer = resolve_identity(
        "MVWP586GW",
        "MVWP586GW Washer Wh - Display",
        "-- Unbranded --",
        "-- No DIB Brand --",
        "Appliance Dealers Cooperative (APPDE)",
    )
    assert washer.brand_key == "Maytag"
    assert "maytag.com" in washer.domains

    finyl = resolve_identity(
        "73019603",
        "Finyline Wh 6' Fl Rail Kit Sq",
        "-- Unbranded --",
        "-- No DIB Brand --",
        "-",
    )
    rdi = resolve_identity(
        "73012503",
        "4x4 Wh Heritage Post Trim RDI",
        "-- Unbranded --",
        "-- No DIB Brand --",
        "-",
    )
    latch = resolve_identity(
        "73002252",
        "Black Gate Gravity Latch RDI",
        "-- Unbranded --",
        "-- No DIB Brand --",
        "-",
    )
    assert finyl.brand_key == rdi.brand_key == latch.brand_key == "RDI"
    assert finyl.domains == rdi.domains == ["rdirail.com"]

    patriot = resolve_identity(
        "SPB-44BPL",
        'Patriot 4"x4"x37"/43" Adjustable Self Leveling Support Post',
        "-- Unbranded --",
        "-- No DIB Brand --",
        "-",
    )
    assert patriot.brand_key == "Color Guard"
    assert patriot.domains == ["colorguardrailing.com"]

    ice = resolve_identity(
        "7547",
        "Ice Guard OC Weathr Lk Mat 2sq",
        "-- Unbranded --",
        "-- No DIB Brand --",
        "-",
    )
    henry = resolve_identity(
        "2733",
        "3'x65' Henry Eaveguard - Ice Guard",
        "-- Unbranded --",
        "-- No DIB Brand --",
        "Palmer Donavin Mfg Company (PALDO)",
    )
    assert ice.brand_key == "Owens Corning"
    assert ice.domains == ["owenscorning.com"]
    assert henry.brand_key == "Henry"

    fisch = resolve_identity(
        "37300952",
        '095842 Fisch Plug Cutter 3/8"',
        "-- Unbranded --",
        "-- No DIB Brand --",
        "-",
    )
    mafell = resolve_identity(
        "924422",
        "924422 Mafell Carpentry - Planing Machine ZH 320 Ec 120V",
        "-- Unbranded --",
        "-- No DIB Brand --",
        "-",
    )
    jig = resolve_identity(
        "TP-1935",
        "TP-1935 Hole Drilling System",
        "-- Unbranded --",
        "-- No DIB Brand --",
        "-",
    )
    assert fisch.brand_key == "Fisch" and fisch.domains == ["fisch-tools.com"]
    assert mafell.brand_key == "Mafell" and "produkte.mafell.de" in mafell.domains
    assert jig.brand_key == "True Position" and jig.domains == ["truepositiontools.com"]


def test_locknlube_westwood_and_southwire_cord_from_remaining_rows():
    gauge = resolve_identity(
        "LNL65301",
        "LNL65301 Digital Tire Pressure - Inflator Gauge",
        "-- Unbranded --",
        "-- No DIB Brand --",
        "-",
    )
    assert gauge.brand_key == "LockNLube"
    assert gauge.domains == ["locknlube.com"]

    lumber = resolve_identity(
        "1513577",
        "1x8-12' Doug Fir STK Smooth 1S2E",
        "COMMODITY - UNBRANDED",
        "-- No DIB Brand --",
        "Westwood Lumber Sales (WESLU)",
    )
    assert lumber.brand_key == "Westwood"
    assert lumber.domains == ["westwoodlumbersales.com"]

    so_cord = resolve_identity(
        "12-4 SO",
        "12-4 SO Cord (Linear Foot)",
        "-- Unbranded --",
        "-- No DIB Brand --",
        "-",
    )
    coleman = resolve_identity(
        "23346-0408",
        "23346-0408 Wire 16/3 SJEWA 250 (Linear Foot)",
        "-- Unbranded --",
        "-- No DIB Brand --",
        "-",
    )
    labeled = resolve_identity(
        "10-4 SO",
        "10-4 SO Cord (Linear Foot)",
        "-- Unbranded --",
        "-- No DIB Brand --",
        "Southwire/g Turner (6603)",
    )
    assert so_cord.brand_key == coleman.brand_key == labeled.brand_key == "Southwire"
    assert "southwire.com" in so_cord.domains


def test_rees_house_mortar_is_rees_not_solomon():
    rees = resolve_identity(
        "25-A",
        "Charcoal Black 25-A Mortar - Type N",
        "-- Unbranded --",
        "-- No DIB Brand --",
        "Rees Cast Stone Company (REECA)",
    )
    buff = resolve_identity(
        "59-J",
        "Light Buff 59-J Mortar - Type N",
        "-- Unbranded --",
        "-- No DIB Brand --",
        "Rees Cast Stone Company (REECA)",
    )
    assert rees.brand_key == buff.brand_key == "Rees Cast Stone"
    assert rees.domains == ["classicstatuary.com"]
    assert rees.manufacturer_name == "Rees Cast Stone Company, Inc."
