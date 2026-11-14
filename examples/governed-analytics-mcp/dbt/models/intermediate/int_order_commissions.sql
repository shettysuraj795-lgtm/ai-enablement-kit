-- Commission charged and refunded per order, in the order's currency.
select
    order_id,
    coalesce(sum(commission_amount) filter (where entry_type = 'charge'), 0) as commission_amount,
    coalesce(sum(commission_amount) filter (where entry_type = 'refund'), 0) as commission_refunded_amount
from {{ ref('stg_commissions') }}
group by order_id
