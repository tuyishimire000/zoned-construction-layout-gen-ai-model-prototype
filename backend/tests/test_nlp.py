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
