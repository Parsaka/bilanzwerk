-- Filing list from the submissions bulk file, latest load wins. Event flags per filing:
--   8-K Item 1.03 (Bankruptcy or Receivership)  -> main label
--   Form 15 (deregistration), Form 25 (delisting) -> sensitivity "distress" label
--   NT 10-K / NT 10-Q (late filing notice)        -> data signal feature
with source as (
    select * from {{ source('sec_submissions', 'filings') }}
),

statement_filers as (
    -- CIKs with financial statements (FSDS), all quarters
    select distinct cast(cik as {{ dbt.type_bigint() }}) as cik
    from {{ source('sec_fsds', 'sub') }}
),

latest as (
    -- one CIK per accession. A filing listed under several CIKs (a joint 8-K of a parent and
    -- its subsidiaries, a Form 25-NSE filed by the exchange for the delisted company) goes to:
    -- not the exchange that filed a 25-NSE (the CIK in the accession prefix), then a CIK with
    -- financial statements, then the lowest CIK, so the choice is the same on every run
    select
        source.*,
        row_number() over (
            partition by source.accession_number
            order by
                source.load_date desc,
                case
                    when
                        source.form like '25-NSE%'
                        and cast(source.cik as {{ dbt.type_bigint() }})
                        = cast(left(source.accession_number, 10) as {{ dbt.type_bigint() }})
                        then 1
                    else 0
                end,
                case when sf.cik is null then 1 else 0 end,
                source.cik
        ) as rn
    from source
    left join statement_filers as sf
        on cast(source.cik as {{ dbt.type_bigint() }}) = sf.cik
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
    typed.accession_number as filing_bk,
    'CIK' as company_bk_type,
    cast(typed.cik as {{ bw_string(20) }}) as company_bk,
    typed.*,
    case when typed.form in ('8-K', '8-K/A') and {{ bw_contains('items', '1.03') }} then 1 else 0 end as is_bankruptcy_8k,
    case when typed.form like '15%' then 1 else 0 end as is_form_15,
    case when typed.form like '25%' then 1 else 0 end as is_form_25,
    case when typed.form like 'NT 10-K%' or typed.form like 'NT 10-Q%' or typed.form like 'NT 20-F%' then 1 else 0 end as is_late_filing_notice,
    {{ bw_hash_diff(["form", "filing_date", "items"]) }} as hd_event,
    coalesce(typed.accepted_at, cast(typed.filing_date as {{ bw_timestamp() }})) as effective_from,
    {{ bw_run_ts() }} as load_datetime,
    cast('sec_submissions.filings' as {{ bw_string(50) }}) as record_source
from typed
