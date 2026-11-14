-- Recomputes monthly EUR totals for paid orders straight from the raw tables
-- and the FX seed, without any staging or intermediate model, and returns
-- every month where they differ from fct_orders. The golden eval answers are
-- computed from the marts, so this keeps a mart bug from becoming the
-- expected answer.
with fx as (
    select rate_date, currency, eur_per_unit from {{ ref('fx_rates') }}
),

refunds as (
    select order_id, sum(amount) as amount
    from {{ source('raw', 'refunds') }}
    group by order_id
),

commissions as (
    select
        order_id,
        sum(amount) filter (where entry_type = 'charge') as charged,
        coalesce(sum(amount) filter (where entry_type = 'refund'), 0) as refunded
    from {{ source('raw', 'commissions') }}
    group by order_id
),

from_raw as (
    select
        date_trunc('month', cast(orders.ordered_at as date)) as month,
        count(*) as paid_orders,
        sum(round(orders.amount * fx.eur_per_unit, 2)) as gross_eur,
        sum(round(coalesce(refunds.amount, 0) * fx.eur_per_unit, 2)) as refund_eur,
        sum(round(commissions.charged * fx.eur_per_unit, 2)
            - round(commissions.refunded * fx.eur_per_unit, 2)) as net_commission_eur
    from {{ source('raw', 'orders') }} as orders
    join fx on orders.currency = fx.currency and cast(orders.ordered_at as date) = fx.rate_date
    left join refunds on orders.order_id = refunds.order_id
    left join commissions on orders.order_id = commissions.order_id
    where orders.payment_status = 'paid'
    group by month
),

from_mart as (
    select
        date_trunc('month', order_date) as month,
        count(*) as paid_orders,
        sum(gross_amount_eur) as gross_eur,
        sum(refund_amount_eur) as refund_eur,
        sum(net_commission_eur) as net_commission_eur
    from {{ ref('fct_orders') }}
    where is_paid
    group by month
)

select *
from from_raw
full outer join from_mart using (month)
where from_raw.paid_orders is distinct from from_mart.paid_orders
    or from_raw.gross_eur is distinct from from_mart.gross_eur
    or from_raw.refund_eur is distinct from from_mart.refund_eur
    or from_raw.net_commission_eur is distinct from from_mart.net_commission_eur
