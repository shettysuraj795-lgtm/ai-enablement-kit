select
    model_id,
    brand,
    model_name,
    category as listing_category
from {{ source('raw', 'watch_models') }}
