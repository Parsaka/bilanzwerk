select
    currency_code as currency_key,
    currency_code,
    currency_name
from {{ ref('currencies') }}
union all
select
    'shares',
    'shares',
    'Number of shares'
