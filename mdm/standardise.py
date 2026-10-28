"""Name and address standardisation for company matching. Originals are always kept."""

from __future__ import annotations

import math
import re
import unicodedata

# Legal-form suffixes that carry no identity. Order matters: longer forms first.
LEGAL_SUFFIXES = [
    "INCORPORATED",
    "CORPORATION",
    "COMPANY",
    "LIMITED",
    "HOLDINGS",
    "HOLDING",
    "AKTIENGESELLSCHAFT",
    "GESELLSCHAFT MIT BESCHRANKTER HAFTUNG",
    "SOCIETAS EUROPAEA",
    "SOCIETE ANONYME",
    "NAAMLOZE VENNOOTSCHAP",
    "SOCIETA PER AZIONI",
    "PUBLIC LIMITED COMPANY",
    "LIMITED PARTNERSHIP",
    "LIMITED LIABILITY COMPANY",
    "GMBH AND CO KGAA",
    "GMBH AND CO KG",
    "AG AND CO KGAA",
    "AG AND CO KG",
    "AND CO",
    "GMBH",
    "KGAA",
    "SE",
    "AG",
    "NV",
    "BV",
    "SA",
    "SPA",
    "PLC",
    "LTD",
    "LLC",
    "LP",
    "LLP",
    "INC",
    "CORP",
    "CO",
    "KG",
    "AB",
    "AS",
    "ASA",
    "OYJ",
    "SAS",
]
ABBREVIATIONS = {
    "INTL": "INTERNATIONAL",
    "INTERNATL": "INTERNATIONAL",
    "TECH": "TECHNOLOGIES",
    "TECHNOLOGY": "TECHNOLOGIES",
    "SVCS": "SERVICES",
    "SVC": "SERVICES",
    "MFG": "MANUFACTURING",
    "PHARM": "PHARMACEUTICALS",
    "PHARMA": "PHARMACEUTICALS",
    "COMMS": "COMMUNICATIONS",
    "&": "AND",
    "BANCORP": "BANCORPORATION",
    "GRP": "GROUP",
    "SYS": "SYSTEMS",
    "NATL": "NATIONAL",
}
_SUFFIX_RE = re.compile(r"(?:\s(?:" + "|".join(re.escape(s) for s in LEGAL_SUFFIXES) + r"))+$")
_NON_ALNUM = re.compile(r"[^A-Z0-9 ]+")
_SPACES = re.compile(r"\s+")
# SEC conformed names sometimes carry a state or a former-name hint: "ACME CORP /DE/"
_SEC_STATE_TAG = re.compile(r"\s*/[A-Z]{2}/?\s*$")


def _text(value: object) -> str | None:
    """Missing values arrive as None, NaN (pandas) or blanks; anything else as text."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    text = str(value).strip()
    return text or None


def ascii_upper(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.upper().replace("ß", "SS")


def standardise_name(name: str | None) -> str | None:
    """'Apple Inc.' -> 'APPLE'; 'Siemens Aktiengesellschaft' -> 'SIEMENS'; 'ACME CORP /DE/' -> 'ACME'."""
    name = _text(name)
    if name is None:
        return None
    text = ascii_upper(name)
    text = _SEC_STATE_TAG.sub("", text)
    text = text.replace("&", " AND ")
    text = _NON_ALNUM.sub(" ", text.replace(".", ""))
    tokens = [ABBREVIATIONS.get(t, t) for t in _SPACES.sub(" ", text).strip().split(" ")]
    text = " ".join(tokens)
    if text.startswith("THE "):
        text = text[4:]
    stripped = _SUFFIX_RE.sub("", text).strip()
    return stripped or text


def standardise_postal_code(code: str | None, country: str | None) -> str | None:
    code = _text(code)
    if code is None:
        return None
    code = ascii_upper(code).replace(" ", "").replace("-", "")
    if (_text(country) or "").upper() == "US":
        code = code[:5]
    return code or None


def standardise_city(city: str | None) -> str | None:
    city = _text(city)
    if city is None:
        return None
    text = _NON_ALNUM.sub(" ", ascii_upper(city))
    return _SPACES.sub(" ", text).strip() or None


US_STATES = {
    "AL",
    "AK",
    "AZ",
    "AR",
    "CA",
    "CO",
    "CT",
    "DE",
    "FL",
    "GA",
    "HI",
    "ID",
    "IL",
    "IN",
    "IA",
    "KS",
    "KY",
    "LA",
    "ME",
    "MD",
    "MA",
    "MI",
    "MN",
    "MS",
    "MO",
    "MT",
    "NE",
    "NV",
    "NH",
    "NJ",
    "NM",
    "NY",
    "NC",
    "ND",
    "OH",
    "OK",
    "OR",
    "PA",
    "RI",
    "SC",
    "SD",
    "TN",
    "TX",
    "UT",
    "VT",
    "VA",
    "WA",
    "WV",
    "WI",
    "WY",
    "DC",
    "PR",
}


def sec_country(state_or_country: str | None) -> str | None:
    """SEC business address 'stateOrCountry' is a US state code or an EDGAR country code."""
    code = _text(state_or_country)
    if code is None:
        return None
    code = code.upper()
    return "US" if code in US_STATES else None
