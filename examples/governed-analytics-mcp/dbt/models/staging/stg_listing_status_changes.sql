select
    listing_id,
    status,
    changed_on
from {{ source('raw', 'listing_status_changes') }}
