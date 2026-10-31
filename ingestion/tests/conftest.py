from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from ingestion.common.config import Settings

SUB = (
    "adsh\tcik\tname\tsic\tcountryba\tstprba\tcityba\tzipba\tcountryinc\tformer\tchanged\tafs\tfye\t"
    "form\tperiod\tfy\tfp\tfiled\taccepted\tprevrpt\tdetail\tinstance\tnciks\taciks\n"
    "0000320193-24-000123\t320193\tAPPLE INC\t3571\tUS\tCA\tCUPERTINO\t95014\tUS\t\t\t1-LAF\t0928\t"
    "10-K\t20240930\t2024\tFY\t20241101\t2024-11-01 06:01:00.0\t0\t1\taapl-20240928_htm.xml\t1\t\n"
    "0000012345-24-000001\t12345\tTINY CORP\t5812\tUS\tNY\tNEW YORK\t10001\tUS\t\t\t5-SML\t1231\t"
    "10-Q\t20240630\t2024\tQ2\t20240807\t2024-08-07 16:30:12.0\t1\t0\ttiny-20240630.htm\t1\t\n"
)
NUM = (
    "adsh\ttag\tversion\tddate\tqtrs\tuom\tsegments\tcoreg\tvalue\tfootnote\n"
    "0000320193-24-000123\tRevenues\tus-gaap/2024\t20240930\t4\tUSD\t\t\t391035000000\t\n"
    "0000320193-24-000123\tRevenues\tus-gaap/2024\t20230930\t4\tUSD\t\t\t383285000000\t\n"
    "0000320193-24-000123\tAssets\tus-gaap/2024\t20240930\t0\tUSD\t\t\t364980000000\t\n"
    "0000320193-24-000123\tRevenues\tus-gaap/2024\t20240930\t4\tUSD\tProductOrService=iPhone;\t\t201183000000\t\n"
    "0000012345-24-000001\tAccountsReceivableNetCurrent\tus-gaap/2024\t20240630\t0\tUSD\t\t\t1234.56\t\n"
)
TAG = (
    "tag\tversion\tcustom\tabstract\tdatatype\tiord\tcrdr\ttlabel\tdoc\n"
    "Revenues\tus-gaap/2024\t0\t0\tmonetary\tD\tC\tRevenues\tAmount of revenue.\n"
    "Assets\tus-gaap/2024\t0\t0\tmonetary\tI\tD\tAssets\tSum of assets.\n"
)
PRE = (
    "adsh\treport\tline\tstmt\tinpth\trfile\ttag\tversion\tplabel\tnegating\n"
    "0000320193-24-000123\t2\t3\tIS\t0\tH\tRevenues\tus-gaap/2024\tTotal net sales\t0\n"
    "0000320193-24-000123\t4\t10\tBS\t0\tH\tAssets\tus-gaap/2024\tTotal assets\t0\n"
)


def make_fsds_zip(path: Path, num: str = NUM, sub: str = SUB) -> Path:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("sub.txt", sub)
        zf.writestr("num.txt", num)
        zf.writestr("tag.txt", TAG)
        zf.writestr("pre.txt", PRE)
        zf.writestr("readme.htm", "<html></html>")
    return path


def make_submissions_zip(path: Path) -> Path:
    main = {
        "cik": "0000012345",
        "entityType": "operating",
        "sic": "5812",
        "sicDescription": "Retail-Eating Places",
        "name": "TINY CORP",
        "tickers": ["TINY"],
        "exchanges": ["Nasdaq"],
        "fiscalYearEnd": "1231",
        "stateOfIncorporation": "DE",
        "addresses": {"business": {"city": "NEW YORK", "stateOrCountry": "NY", "zipCode": "10001"}},
        "formerNames": [{"name": "SMALL CORP", "from": "2001-01-01T00:00:00.000Z", "to": "2015-06-30T00:00:00.000Z"}],
        "filings": {
            "recent": {
                "accessionNumber": ["0000012345-24-000009", "0000012345-24-000008", "0000012345-24-000007"],
                "filingDate": ["2024-10-15", "2024-09-01", "2024-08-07"],
                "reportDate": ["2024-10-14", "", "2024-06-30"],
                "acceptanceDateTime": [
                    "2024-10-15T16:05:00.000Z",
                    "2024-09-01T09:00:00.000Z",
                    "2024-08-07T16:30:12.000Z",
                ],
                "form": ["8-K", "SC 13G", "10-Q"],
                "items": ["1.03,9.01", "", ""],
            },
            "files": [{"name": "CIK0000012345-submissions-001.json"}],
        },
    }
    page = {
        "accessionNumber": ["0000012345-10-000001"],
        "filingDate": ["2010-03-01"],
        "reportDate": ["2009-12-31"],
        "acceptanceDateTime": ["2010-03-01T12:00:00.000Z"],
        "form": ["10-K"],
        "items": [""],
    }
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("CIK0000012345.json", json.dumps(main))
        zf.writestr("CIK0000012345-submissions-001.json", json.dumps(page))
    return path


LEI_CSV = (
    '"LEI","Entity.LegalName","Entity.OtherEntityNames.OtherEntityName.1",'
    '"Entity.LegalAddress.FirstAddressLine","Entity.LegalAddress.MailRouting","Entity.LegalAddress.City",'
    '"Entity.LegalAddress.Country","Entity.LegalAddress.PostalCode",'
    '"Entity.HeadquartersAddress.FirstAddressLine","Entity.HeadquartersAddress.City",'
    '"Entity.HeadquartersAddress.Country","Entity.HeadquartersAddress.PostalCode",'
    '"Entity.EntityStatus","Registration.RegistrationStatus"\n'
    '"HWUPKR0MPOU8FGXBT394","Apple Inc.","AAPL","c/o Jane Doe, One Apple Park Way","Attn Legal Jane Doe",'
    '"Cupertino","US","95014","One Apple Park Way","Cupertino","US","95014","ACTIVE","ISSUED"\n'
)


def make_gleif_zip(path: Path, csv_text: str = LEI_CSV) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("20241101-0000-gleif-goldencopy-lei2-golden-copy.csv", csv_text)
    return path


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        data_root=tmp_path / "data", user_agent="Bilanzwerk test test@example.com", min_seconds_between_requests=0.0
    )


@pytest.fixture
def fsds_zip(tmp_path: Path) -> Path:
    return make_fsds_zip(tmp_path / "2024q3.zip")


def to_bytes(text: str) -> bytes:
    return io.BytesIO(text.encode()).getvalue()
