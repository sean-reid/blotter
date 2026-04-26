from blotter.stages.extract import (
    extract_addresses,
    extract_landmarks,
    extract_locations,
    normalize_text,
)


class TestNormalizeText:
    def test_expands_abbreviations(self):
        assert "El Camino Real" in normalize_text("respond to ecr and lawrence")

    def test_expands_city_abbreviations(self):
        assert "San Jose" in normalize_text("en route to sj")

    def test_preserves_unmatched_text(self):
        result = normalize_text("nothing to expand here")
        assert result == "nothing to expand here"


class TestExtractAddresses:
    def test_street_address(self):
        locs = extract_addresses("Respond to 1450 Stevens Creek Blvd")
        assert len(locs) >= 1
        assert "1450" in locs[0].raw_text
        assert "Stevens Creek" in locs[0].raw_text

    def test_block_reference(self):
        locs = extract_addresses("Suspect last seen in the 400 block of Main Street")
        assert any("block" in loc.raw_text.lower() for loc in locs)

    def test_intersection(self):
        locs = extract_addresses("Accident at First Street and Santa Clara")
        assert any("and" in loc.raw_text.lower() or "intersection" in loc.source for loc in locs)

    def test_highway_reference(self):
        locs = extract_addresses("Northbound 101 at Great America Parkway")
        assert any("101" in loc.raw_text for loc in locs)

    def test_no_false_positives_on_codes(self):
        locs = extract_addresses("10-4 copy that code 3")
        assert len(locs) == 0


class TestExtractLandmarks:
    def test_finds_valley_fair(self):
        locs = extract_landmarks("shoplifter at valley fair")
        assert len(locs) >= 1
        assert "Santa Clara" in locs[0].normalized or "San Jose" in locs[0].normalized

    def test_finds_vmc(self):
        locs = extract_landmarks("transporting to vmc")
        assert len(locs) >= 1
        assert "San Jose" in locs[0].normalized

    def test_no_match_on_unrelated(self):
        locs = extract_landmarks("unit adam 12 responding")
        assert len(locs) == 0


class TestExtractLocations:
    def test_deduplicates(self):
        locs = extract_locations(
            "Respond to 500 El Camino Real. "
            "Unit en route to 500 El Camino Real."
        )
        normalized_set = {loc.normalized.lower() for loc in locs}
        assert len(normalized_set) == len(locs)

    def test_appends_county_context(self):
        locs = extract_locations("respond to 123 Main Street")
        if locs:
            assert "CA" in locs[0].normalized or "Santa Clara" in locs[0].normalized

    def test_sorts_by_confidence(self):
        locs = extract_locations(
            "respond to valley fair near 2855 Stevens Creek Blvd"
        )
        if len(locs) >= 2:
            assert locs[0].confidence >= locs[1].confidence
