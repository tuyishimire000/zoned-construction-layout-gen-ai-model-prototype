import pytest
from app.nlp.extractor import extract_parameters

def test_extract_parameters():
    desc = "I own a 600 sqm residential plot in Gasabo and want to build a three-story house with parking for two vehicles."
    params = extract_parameters(desc)
    assert params["plot_size"] == 600.0
    assert params["floors"] == 3
    assert params["parking_spaces"] == 2
    assert params["usage"] == "residential"

def test_extract_commercial():
    desc = "We have a 1200 square meters commercial plot, and need 6 floors and parking 10."
    params = extract_parameters(desc)
    assert params["plot_size"] == 1200.0
    assert params["floors"] == 6
    assert params["parking_spaces"] == 10
    assert params["usage"] == "commercial"

def test_extract_multi_sentence():
    desc = "This is a commercial project. The area is 500 m2. We want 4 levels. There should be 15 parking spaces."
    params = extract_parameters(desc)
    assert params["plot_size"] == 500.0
    assert params["floors"] == 4
    assert params["parking_spaces"] == 15
    assert params["usage"] == "commercial"

def test_extract_unstructured():
    desc = "Industrial. floors: 2. area: 1000. cars: 5."
    params = extract_parameters(desc)
    assert params["plot_size"] == 1000.0
    assert params["floors"] == 2
    assert params["parking_spaces"] == 5
    assert params["usage"] == "industrial"

def test_extract_rooms():
    desc = "I want a residential house with 3 bedrooms, 2 bathrooms, 1 kitchen, and 2 offices."
    params = extract_parameters(desc)
    assert params["usage"] == "residential"
    assert params["rooms"]["bedrooms"] == 3
    assert params["rooms"]["bathrooms"] == 2
    assert params["rooms"]["kitchens"] == 1
    assert params["rooms"]["offices"] == 2
