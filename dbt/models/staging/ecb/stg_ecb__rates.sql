-- Daily ECB reference rates, one row per currency and day (latest fetch wins).
with source as (
    select * from {{ source('ecb', 'rates') }}
),

latest as (
    select
        source.*,
        row_number() over (partition by source.currency, source.rate_date order by source.fetch_date desc) as rn
    from source
)

select
    cast(currency as {{ bw_string(3) }}) as currency_code,
    cast(rate_date as date) as rate_date,
    cast(rate_per_eur as decimal(18, 6)) as rate_per_eur
from latest
where rn = 1
