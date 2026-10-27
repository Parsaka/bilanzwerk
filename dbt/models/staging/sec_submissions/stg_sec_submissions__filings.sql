-- Filing list from the submissions bulk file, latest load wins. Event flags per filing:
--   8-K Item 1.03 (Bankruptcy or Receivership)  -> main label
--   Form 15 (deregistration), Form 25 (delisting) -> sensitivity "distress" label
--   NT 10-K / NT 10-Q (late filing notice)        -> data signal feature
with source as (
    select * from {{ source('sec_submissions', 'filings') }}
),

latest as (
    select
        source.*,
        row_number() over (partition by accession_number order by load_date desc) as rn
    from source
),

typed as (
    select
        cast(accession_number as {{ bw_string(20) }}) as accession_number,
        cast(cik as {{ dbt.type_bigint() }}) as cik,
        cast(form as {{ bw_string(20) }}) as form,
        cast(filing_date as date) as filing_date,
        cast(report_date as date) as report_date,
        cast(
            replace(replace(left(acceptance_datetime, 19), 'T', ' '), 'Z', '') as {{ bw_timestamp() }}
        ) as accepted_at,
        cast(items as {{ bw_string(200) }}) as items,
        cast(load_date as {{ bw_string(10) }}) as load_date
    from latest
    where rn = 1
)

select
    {{ bw_hash_key(["accession_number"]) }} as hk_filing,
    {{ bw_hash_key(["'CIK'", "cik"]) }} as hk_company,
    {{ bw_hash_key(["accession_number", "'CIK'", "cik"]) }} as hk_filing_company,
    accession_number as filing_bk,
    'CIK' as company_bk_type,
    cast(cik as {{ bw_string(20) }}) as company_bk,
    typed.*,
    case when form in ('8-K', '8-K/A') and {{ bw_contains('items', '1.03') }} then 1 else 0 end as is_bankruptcy_8k,
    case when form like '15%' then 1 else 0 end as is_form_15,
    case when form like '25%' then 1 else 0 end as is_form_25,
    case when form like 'NT 10-K%' or form like 'NT 10-Q%' or form like 'NT 20-F%' then 1 else 0 end as is_late_filing_notice,
    {{ bw_hash_diff(["form", "filing_date", "items"]) }} as hd_event,
    coalesce(accepted_at, cast(filing_date as {{ bw_timestamp() }})) as effective_from,
    {{ bw_run_ts() }} as load_datetime,
    cast('sec_submissions.filings' as {{ bw_string(50) }}) as record_source
from typed
