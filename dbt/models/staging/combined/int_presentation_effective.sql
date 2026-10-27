-- Presentation rows with an effective time (the run time; presentation never changes per filing).
select
    p.*,
    p.load_datetime as effective_from
from {{ ref('stg_sec_fsds__pre') }} as p
