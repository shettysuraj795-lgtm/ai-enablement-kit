select
    dealer_id,
    dealer_region,
    dealer_tier
from {{ ref('stg_dealers') }}
