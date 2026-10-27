-- Quality SLA (docs/runbook.md): at least 98 % of filings pass the balance check
-- (total assets equal total equity and liabilities within 0.5 %).
select
    count(*) as checked,
    sum(case when abs(ta - tle) <= {{ var('balance_check_tolerance') }} * abs(ta) then 1 else 0 end) as passed
from {{ ref('int_company_period_wide') }}
where version = '{{ var("version_first_reported") }}'
    and ta is not null
    and tle is not null
having count(*) > 0
    and {{ bw_div('sum(case when abs(ta - tle) <= ' ~ var('balance_check_tolerance') ~ ' * abs(ta) then 1 else 0 end)', 'count(*)') }}
        < {{ var('balance_check_target_pass_rate') }}
