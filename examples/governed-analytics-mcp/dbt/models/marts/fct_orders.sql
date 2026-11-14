-- One row per order. Every EUR amount, including refunds and refunded
-- commission, uses the reference rate on the order date (ADR-001).
with orders as (
    select * from {{ ref('stg_orders') }}
),

listings as (
    select * from {{ ref('stg_listings') }}
),

converted as (
    select
        orders.order_id,
        orders.order_date,
        orders.paid_at,
        orders.is_paid,
        orders.buyer_id,
        listings.dealer_id,
        dealers.dealer_region,
        dealers.dealer_tier,
        orders.listing_id,
        watch_models.listing_category,
        orders.order_currency,
        orders.original_amount,
        fx.eur_per_unit as fx_rate,
        fx.rate_date as fx_rate_date,
        round(orders.original_amount * fx.eur_per_unit, 2) as gross_amount_eur,
        round(coalesce(refunds.refund_amount, 0) * fx.eur_per_unit, 2) as refund_amount_eur,
        round(coalesce(commissions.commission_amount, 0) * fx.eur_per_unit, 2) as commission_eur,
        round(coalesce(commissions.commission_refunded_amount, 0) * fx.eur_per_unit, 2) as commission_refunded_eur
    from orders
    left join listings on orders.listing_id = listings.listing_id
    left join {{ ref('dim_dealers') }} as dealers on listings.dealer_id = dealers.dealer_id
    left join {{ ref('stg_watch_models') }} as watch_models on listings.model_id = watch_models.model_id
    left join {{ ref('stg_fx_rates') }} as fx
        on orders.order_currency = fx.currency and orders.order_date = fx.rate_date
    left join {{ ref('int_order_refunds') }} as refunds on orders.order_id = refunds.order_id
    left join {{ ref('int_order_commissions') }} as commissions on orders.order_id = commissions.order_id
)

select
    cast(order_id as varchar) as order_id,
    cast(order_date as date) as order_date,
    cast(paid_at as timestamp) as paid_at,
    cast(is_paid as boolean) as is_paid,
    cast(buyer_id as varchar) as buyer_id,
    cast(dealer_id as varchar) as dealer_id,
    cast(dealer_region as varchar) as dealer_region,
    cast(dealer_tier as varchar) as dealer_tier,
    cast(listing_id as varchar) as listing_id,
    cast(listing_category as varchar) as listing_category,
    cast(order_currency as varchar(3)) as order_currency,
    cast(original_amount as decimal(18, 2)) as original_amount,
    cast(fx_rate as decimal(18, 6)) as fx_rate,
    cast(fx_rate_date as date) as fx_rate_date,
    cast(gross_amount_eur as decimal(18, 2)) as gross_amount_eur,
    cast(refund_amount_eur as decimal(18, 2)) as refund_amount_eur,
    cast(gross_amount_eur - refund_amount_eur as decimal(18, 2)) as net_amount_eur,
    cast(commission_eur as decimal(18, 2)) as commission_eur,
    cast(commission_refunded_eur as decimal(18, 2)) as commission_refunded_eur,
    cast(commission_eur - commission_refunded_eur as decimal(18, 2)) as net_commission_eur
from converted
