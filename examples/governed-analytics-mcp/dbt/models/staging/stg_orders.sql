select
    order_id,
    listing_id,
    buyer_id,
    ordered_at,
    cast(ordered_at as date) as order_date,
    payment_status,
    payment_status = 'paid' as is_paid,
    paid_at,
    currency as order_currency,
    cast(amount as decimal(18, 2)) as original_amount
from {{ source('raw', 'orders') }}
