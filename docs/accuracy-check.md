# Accuracy spot check

Twenty random company-years, compared by hand with the statement as filed on EDGAR (or the
ESEF report). The sample is drawn after the first full load with:

```sql
select c.company_name, c.cik, p.fiscal_year, p.first_filing
from marts.dim_period p join marts.dim_company c on p.company_id = c.company_id and c.is_current = 1
where p.first_form = '10-K'
order by hash(p.period_key) limit 20;
```

For each: revenue, EBIT, total assets, total liabilities, equity, cash from operations. A value
passes when it matches the filed statement after the documented sign rule.

| # | Company | CIK | FY | Filing | Revenue | EBIT | Total assets | Total liabilities | Equity | CFO | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | _to be filled after the first load_ | | | | | | | | | | |

Result: _n of 120 values match_.
