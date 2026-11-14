select
    commission_id,
    order_id,
    refund_id,
    entry_type,
    currency as commission_currency,
    cast(amount as decimal(18, 2)) as commission_amount,
    booked_at
from {{ source('raw', 'commissions') }}
