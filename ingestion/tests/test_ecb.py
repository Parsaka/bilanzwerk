from __future__ import annotations

from datetime import date
from decimal import Decimal

import responses

from ingestion import ecb

CSV = (
    "KEY,FREQ,CURRENCY,CURRENCY_DENOM,EXR_TYPE,EXR_SUFFIX,TIME_PERIOD,OBS_VALUE\n"
    "EXR.D.USD.EUR.SP00.A,D,USD,EUR,SP00,A,2024-01-02,1.0956\n"
    "EXR.D.USD.EUR.SP00.A,D,USD,EUR,SP00,A,2024-01-03,1.0919\n"
    "EXR.D.GBP.EUR.SP00.A,D,GBP,EUR,SP00,A,2024-01-02,0.86518\n"
    "EXR.D.GBP.EUR.SP00.A,D,GBP,EUR,SP00,A,2024-01-03,NaN\n"
)


def test_parse_csv_skips_missing_observations():
    tbl = ecb.parse_csv(CSV)
    assert tbl.num_rows == 3
    rows = tbl.to_pylist()
    assert rows[0] == {"currency": "USD", "rate_date": date(2024, 1, 2), "rate_per_eur": Decimal("1.095600")}


@responses.activate
def test_run_is_incremental_and_idempotent(settings):
    responses.get(ecb.URL.format(currencies="GBP+USD"), body=CSV)
    assert ecb.run(settings, ["USD", "GBP"], start=date(2024, 1, 1), end=date(2024, 1, 3)) == 3
    assert ecb.last_loaded_date(settings) == date(2024, 1, 3)
    # same response again (e.g. a rerun the same day) -> nothing new lands
    assert ecb.run(settings, ["USD", "GBP"], start=date(2024, 1, 1), end=date(2024, 1, 3)) == 0
    # the next default run starts after the last loaded day; nothing to do if that is in the future
    assert ecb.run(settings, ["USD", "GBP"], end=date(2024, 1, 3)) == 0
