select
    dealer_id,
    country_code as dealer_region,
    subscription_tier as dealer_tier,
    currency as dealer_currency,
    joined_on
from {{ source('raw', 'dealers') }}
