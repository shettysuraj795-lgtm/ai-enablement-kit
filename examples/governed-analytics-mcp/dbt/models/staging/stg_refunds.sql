select
    refund_id,
    order_id,
    refunded_at,
    reason,
    currency as refund_currency,
    cast(amount as decimal(18, 2)) as refund_amount
from {{ source('raw', 'refunds') }}
