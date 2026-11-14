-- Seven plausible answers to "What was revenue in Q3 2026?", from one dataset.
-- Only the first three are governed metrics; the rest are the readings an
-- ungoverned query can land on. Compile with `dbt compile` and run the SQL in
-- target/compiled/ against the warehouse.
with q3 as (
    select date '2026-07-01' as q_start, date '2026-10-01' as q_end
),

orders as (
    select * from {{ ref('fct_orders') }}
),

fx as (
    select * from {{ ref('stg_fx_rates') }}
)

select 'gross_merchandise_value (governed)' as reading, sum(gross_amount_eur) as eur
from orders, q3 where is_paid and order_date >= q_start and order_date < q_end

union all
select 'net_merchandise_value (governed)', sum(net_amount_eur)
from orders, q3 where is_paid and order_date >= q_start and order_date < q_end

union all
select 'commission_revenue (governed)', sum(net_commission_eur)
from orders, q3 where is_paid and order_date >= q_start and order_date < q_end

union all
-- Unpaid orders included: failed and pending payments counted as sales.
select 'gross, including unpaid orders', sum(gross_amount_eur)
from orders, q3 where order_date >= q_start and order_date < q_end

union all
-- Payment date instead of order date, for both the period and the FX rate.
select 'gross, by payment date and payment-date rate', sum(round(o.original_amount * fx.eur_per_unit, 2))
from orders as o
join fx on o.order_currency = fx.currency and cast(o.paid_at as date) = fx.rate_date, q3
where o.is_paid and o.paid_at >= q_start and o.paid_at < q_end

union all
-- Refunds deducted in the quarter they were made, not the quarter of the order.
select 'net, refunds by refund date', (
    select sum(gross_amount_eur) from orders, q3 where is_paid and order_date >= q_start and order_date < q_end
) - (
    select sum(round(r.refund_amount * o.fx_rate, 2))
    from {{ ref('stg_refunds') }} as r join orders as o using (order_id), q3
    where r.refunded_at >= q_start and r.refunded_at < q_end
)

union all
-- Net as it looked on 1 Oct 2026: late refunds had not arrived yet.
select 'net, as known on 1 Oct 2026', (
    select sum(gross_amount_eur) from orders, q3 where is_paid and order_date >= q_start and order_date < q_end
) - (
    select coalesce(sum(round(r.refund_amount * o.fx_rate, 2)), 0)
    from {{ ref('stg_refunds') }} as r join orders as o using (order_id), q3
    where o.is_paid and o.order_date >= q_start and o.order_date < q_end and r.refunded_at < q_end
)
