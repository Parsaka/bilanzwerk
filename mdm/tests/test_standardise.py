import pytest

from mdm.standardise import name_marks, sec_country, standardise_city, standardise_name, standardise_postal_code


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Apple Inc.", "APPLE"),
        ("APPLE INC", "APPLE"),
        ("Siemens Aktiengesellschaft", "SIEMENS"),
        ("SAP SE", "SAP"),
        ("Bayerische Motoren Werke AG", "BAYERISCHE MOTOREN WERKE"),
        ("ACME CORP /DE/", "ACME"),
        ("The Coca-Cola Company", "COCA COLA"),
        ("Johnson & Johnson", "JOHNSON AND JOHNSON"),
        ("Müller GmbH & Co. KG", "MULLER"),
        ("Intl Business Machines Corp", "INTERNATIONAL BUSINESS MACHINES"),
        ("Holding", "HOLDING"),  # never strip a name to nothing
        ("KINDER MORGAN ENERGY PARTNERS L P", "KINDER MORGAN ENERGY PARTNERS"),
        ("CANADIAN IMPERIAL BANK OF COMMERCE /CAN/", "CANADIAN IMPERIAL BANK OF COMMERCE"),
        ("Alight, Inc. / Delaware", "ALIGHT"),
        ("California BanCorp \\ CA", "CALIFORNIA BANCORPORATION"),
        ("Nate's Foods Co.", "NATES FOODS"),
        ("NOVO NORDISK A/S", "NOVO NORDISK"),
        (None, None),
    ],
)
def test_standardise_name(raw, expected):
    assert standardise_name(raw) == expected


def test_postal_and_city():
    assert standardise_postal_code("95014-2083", "US") == "95014"
    assert standardise_postal_code("80 333", "DE") == "80333"
    assert standardise_city("São Paulo") == "SAO PAULO"
    assert sec_country("CA") == "US"
    assert sec_country("X1") is None


def test_missing_values_from_pandas_are_none():
    """pandas gives NaN for empty address fields (seen in the real GLEIF and SEC data)."""
    nan = float("nan")
    assert standardise_city(nan) is None
    assert standardise_name(nan) is None
    assert standardise_postal_code(nan, "US") is None
    assert standardise_postal_code("10001-1234", nan) == "100011234"
    assert sec_country(nan) is None
    assert standardise_postal_code(10001, "US") == "10001"


def test_name_marks():
    assert name_marks("ATLAS RESOURCES PUBLIC 18 2009 C") == "18|2009|C"
    assert name_marks("VENTURE LENDING AND LEASING IX") == "IX"
    assert name_marks("WASTE CONNECTIONS US") == "US"
    assert name_marks("APPLE") == ""
    assert name_marks(None) == ""
