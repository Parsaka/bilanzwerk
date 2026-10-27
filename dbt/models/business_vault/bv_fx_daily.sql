-- Daily EUR reference rates for every calendar day: the closing rate is the last published
-- rate on or before the day; cumulative sums over published days let the marts compute the
-- average rate of any period with two lookups instead of a range join.
with spine as (
    {{ bw_date_spine('1999-01-01', '2030-12-31') }}
),

currencies as (
    select distinct currency_code from {{ ref('stg_ecb__rates') }}
),

grid as (
    select
        c.currency_code,
        s.date_day
    from currencies as c
    cross join spine as s
),

joined as (
    select
        g.currency_code,
        g.date_day,
        r.rate_per_eur,
        case when r.rate_per_eur is not null then 1 else 0 end as is_published
    from grid as g
    left join {{ ref('stg_ecb__rates') }} as r
        on
            g.currency_code = r.currency_code
            and g.date_day = r.rate_date
),

filled as (
    select
        joined.*,
        max(case when joined.is_published = 1 then joined.date_day end) over (
            partition by joined.currency_code order by joined.date_day rows between unbounded preceding and current row
        ) as last_published_day,
        sum(cast(coalesce(joined.rate_per_eur, 0) as {{ bw_float() }})) over (
            partition by joined.currency_code order by joined.date_day rows between unbounded preceding and current row
        ) as cum_rate_sum,
        sum(joined.is_published) over (
            partition by joined.currency_code order by joined.date_day rows between unbounded preceding and current row
        ) as cum_published_days
    from joined
)

select
    f.currency_code,
    f.date_day,
    cast(r.rate_per_eur as {{ bw_float() }}) as closing_rate_per_eur,
    f.cum_rate_sum,
    f.cum_published_days
from filled as f
left join {{ ref('stg_ecb__rates') }} as r
    on
        f.currency_code = r.currency_code
        and f.last_published_day = r.rate_date

union all

-- EUR itself: rate 1 every day
select
    'EUR',
    s.date_day,
    cast(1 as {{ bw_float() }}),
    cast({{ dbt.datediff("cast('1999-01-01' as date)", 's.date_day', 'day') }} + 1 as {{ bw_float() }}),
    {{ dbt.datediff("cast('1999-01-01' as date)", 's.date_day', 'day') }} + 1
from spine as s
