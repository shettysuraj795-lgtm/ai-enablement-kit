{#- Fails for every row where the expression is false or null. On a column,
    the expression is appended to the column name, e.g. `= 1` or
    `between 0 and gross_amount_eur`. -#}
{% test expression_is_true(model, expression, column_name=none) %}
select *
from {{ model }}
where not coalesce(({% if column_name %}{{ column_name }} {% endif %}{{ expression }}), false)
{% endtest %}
