import pytest
from opol import OPOL

@pytest.fixture
def opol_instance():
    # Setup code: create an OPOL instance
    return OPOL(mode="container")

def test_geojson(opol_instance):
    # Use the fixture
    geojson = opol_instance.geo.json_by_event("War", limit=5)
    assert geojson is not None, "GeoJSON should not be None"
    assert len(geojson) > 0, "GeoJSON should contain data"

def test_berlin_coords(opol_instance):
    # Use the fixture
    berlin_coords = opol_instance.geo.code("Berlin")["coordinates"]
    assert berlin_coords is not None, "Berlin coordinates should not be None"
    assert len(berlin_coords) == 2, "Berlin coordinates should have two elements"

if __name__ == "__main__":
    pytest.main()