-- Calendar for as-of dates, events and period ends.
with spine as (
    {{ bw_date_spine('2005-01-01', '2030-12-31') }}
)

select
    date_day as date_key,
    date_day,
    year(date_day) as calendar_year,
    cast({{ bw_intdiv('month(date_day) - 1', '3') }} + 1 as {{ dbt.type_int() }}) as calendar_quarter,
    month(date_day) as calendar_month,
    case month(date_day)
        when 1 then 'Januar' when 2 then 'Februar' when 3 then 'März' when 4 then 'April'
        when 5 then 'Mai' when 6 then 'Juni' when 7 then 'Juli' when 8 then 'August'
        when 9 then 'September' when 10 then 'Oktober' when 11 then 'November' else 'Dezember'
    end as month_name_de,
    {{ bw_month_end('date_day') }} as month_end_date,
    case when date_day = {{ bw_month_end('date_day') }} then 1 else 0 end as is_month_end,
    year(date_day) * 100 + month(date_day) as year_month
from spine
