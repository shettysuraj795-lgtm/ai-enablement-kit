-- Raw listings contain rows loaded twice by a replayed export. Keep the most
-- recently loaded row per listing.
select
    listing_id,
    dealer_id,
    model_id,
    condition,
    asking_price,
    currency as listing_currency,
    created_at,
    cast(created_at as date) as created_date
from {{ source('raw', 'listings') }}
qualify row_number() over (partition by listing_id order by _loaded_at desc) = 1
