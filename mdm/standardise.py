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
    "COMPANY": "CO",
}
_SUFFIX_RE = re.compile(r"(?:\s(?:" + "|".join(re.escape(s) for s in LEGAL_SUFFIXES) + r"))+$")
_NON_ALNUM = re.compile(r"[^A-Z0-9 ]+")
_SPACES = re.compile(r"\s+")
# SEC conformed names sometimes carry a state or country tag: "ACME CORP /DE/", "BANK /CAN/",
# "ALIGHT, INC. / DELAWARE", "CALIFORNIA BANCORP \\ CA". One letter after a slash is part of the
# name ("NOVO NORDISK A/S"), so a tag needs two letters or more.
_SEC_STATE_TAG = re.compile(r"\s*(?:/\s*[A-Z]{2,}\s*/?|\\\s*[A-Z]{2,})\s*$")
# Letters spelled one by one ("L P", "J P MORGAN") are joined, so they meet "LP", "JPMORGAN".
_LETTER_RUN = re.compile(r"\b(?:[A-Z] )+[A-Z]\b")
_APOSTROPHE = re.compile(r"['\u2019`]")
# Tokens that tell series, vehicles and country units apart: roman numerals, anything with a
# digit, single letters and a few vehicle words (REVIEW.md rule N1/N2). If both names do not carry
# the same set, the pair is not the same legal entity.
_ROMAN = re.compile(r"^(?=[IVXL])(?:XL|L?X{0,3})(?:IX|IV|V?I{0,3})$")
MARK_WORDS = {
    "US",
    "USA",
    "NA",
    "UK",
    "PE",
    "TE",
    "SPV",
    "FEEDER",
    "MASTER",
    "OFFSHORE",
    "ONSHORE",
    "INTERMEDIATE",
    "SERIES",
}


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
    text = _normalised(name)
    if text is None:
        return None
    stripped = _SUFFIX_RE.sub("", text).strip()
    return stripped or text


def _normalised(name: str | None) -> str | None:
    """Upper case, tags and punctuation removed, abbreviations expanded; legal form still on."""
    name = _text(name)
    if name is None:
        return None
    text = ascii_upper(name)
    text = _SEC_STATE_TAG.sub("", text)
    text = text.replace("&", " AND ")
    text = _NON_ALNUM.sub(" ", _APOSTROPHE.sub("", text.replace(".", "")))
    text = _LETTER_RUN.sub(lambda m: m.group(0).replace(" ", ""), _SPACES.sub(" ", text).strip())
    text = " ".join(ABBREVIATIONS.get(t, t) for t in text.split(" "))
    return text[4:] if text.startswith("THE ") else text


# Legal forms grouped into families: "Inc", "Corp" and "Co" are one US corporation form, an LLC or
# an LP is another entity type. Holding words are not a form. A different family with the same
# name is the typical subsidiary pattern ("Amazon.com, LLC" vs "Amazon.com, Inc.").
_FORM_FAMILY = {
    "INCORPORATED": "CORP", "CORPORATION": "CORP", "INC": "CORP", "CORP": "CORP", "CO": "CORP",
    "LLC": "LLC", "LIMITED LIABILITY COMPANY": "LLC",
    "LP": "LP", "LLP": "LP", "LIMITED PARTNERSHIP": "LP",
    "LIMITED": "LTD", "LTD": "LTD", "PLC": "PLC", "PUBLIC LIMITED COMPANY": "PLC",
    "AKTIENGESELLSCHAFT": "AG", "AG": "AG", "SOCIETAS EUROPAEA": "SE", "SE": "SE",
    "NAAMLOZE VENNOOTSCHAP": "NV", "NV": "NV", "BV": "BV", "SOCIETE ANONYME": "SA", "SA": "SA",
}  # fmt: skip
_FORM_RE = re.compile(r"\s(" + "|".join(re.escape(s) for s in sorted(_FORM_FAMILY, key=len, reverse=True)) + r")$")
_HOLDING_TAIL = re.compile(r"\s(?:HOLDINGS|HOLDING|AND CO)$")


def legal_form(name: str | None) -> str | None:
    """Family of the legal form at the end of a name: 'Amazon.com, LLC' -> 'LLC', 'Apple Inc.' -> 'CORP'."""
    text = _normalised(name)
    if text is None:
        return None
    while True:
        m = _FORM_RE.search(text)
        if m:
            return _FORM_FAMILY[m.group(1)]
        shorter = _HOLDING_TAIL.sub("", text)
        if shorter == text:
            return None
        text = shorter


def name_marks(name_std: str | None) -> str:
    """The distinguishing tokens of a standardised name, sorted and joined: 'FUND II 2008' -> '2008|II'."""
    if not name_std:
        return ""
    marks = {t for t in name_std.split(" ") if _ROMAN.match(t) or any(ch.isdigit() for ch in t) or len(t) == 1}
    return "|".join(sorted(marks | (set(name_std.split(" ")) & MARK_WORDS)))


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
