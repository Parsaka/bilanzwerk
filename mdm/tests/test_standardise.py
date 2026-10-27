import pytest

from mdm.standardise import sec_country, standardise_city, standardise_name, standardise_postal_code


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
