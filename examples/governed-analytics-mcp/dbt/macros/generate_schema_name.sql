{#- Use custom schema names as they are (`marts`, not `main_marts`), so the
    compiler and the MCP server can address `marts.fct_orders` directly. -#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
