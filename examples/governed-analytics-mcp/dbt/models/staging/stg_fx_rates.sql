select
    rate_date,
    currency,
    cast(eur_per_unit as decimal(18, 6)) as eur_per_unit
from {{ ref('fx_rates') }}
