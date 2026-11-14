-- Turns status changes into date ranges. A sold or withdrawn listing ends on
-- the day of that change; an open listing runs to the snapshot end date.
with changes as (
    select
        listing_id,
        status,
        changed_on,
        lead(changed_on) over (partition by listing_id order by changed_on) as next_changed_on
    from {{ ref('stg_listing_status_changes') }}
)

select
    listing_id,
    status,
    changed_on as valid_from,
    case
        when status in ('sold', 'withdrawn') then changed_on
        when next_changed_on is not null then next_changed_on - interval 1 day
        else date '{{ var("snapshot_end_date") }}'
    end::date as valid_to
from changes
