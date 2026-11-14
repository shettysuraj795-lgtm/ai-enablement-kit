-- All refunds per order, in the order's currency. Refunds are attributed to
-- the order, whatever date they were made on.
select
    order_id,
    sum(refund_amount) as refund_amount,
    count(*) as refund_count,
    max(refunded_at) as last_refunded_at
from {{ ref('stg_refunds') }}
group by order_id
