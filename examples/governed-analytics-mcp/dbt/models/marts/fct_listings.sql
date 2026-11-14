-- One row per listing per day, from the day it was created until the day it
-- was sold or withdrawn, or the snapshot end date if still open. A listing is
-- active on a day if its status at the end of that day is `active`.
with daily_status as (
    select
        listing_id,
        cast(unnest(generate_series(valid_from, valid_to, interval 1 day)) as date) as snapshot_date,
        status
    from {{ ref('int_listing_status_intervals') }}
    where valid_from <= valid_to
)

select
    cast(daily_status.listing_id as varchar) as listing_id,
    daily_status.snapshot_date,
    daily_status.status = 'active' as is_active,
    cast(listings.dealer_id as varchar) as dealer_id,
    cast(dealers.dealer_region as varchar) as dealer_region,
    cast(dealers.dealer_tier as varchar) as dealer_tier,
    cast(watch_models.listing_category as varchar) as listing_category
from daily_status
left join {{ ref('stg_listings') }} as listings on daily_status.listing_id = listings.listing_id
left join {{ ref('dim_dealers') }} as dealers on listings.dealer_id = dealers.dealer_id
left join {{ ref('stg_watch_models') }} as watch_models on listings.model_id = watch_models.model_id
