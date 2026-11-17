# Architecture: governed analytics MCP server

How a question becomes a number, and what is recorded on the way. Design choices and their reasons are in [DESIGN.md](DESIGN.md); the formats on each arrow are in [docs/contracts](../../docs/contracts/).

**The rule the whole design follows:** the model chooses *what* to ask for; code decides *how* it is computed. SQL on the governed path is never written by the model.

## Workflow: how a question becomes a number

```mermaid
flowchart LR
    U["User"]
    AG["Agent in Claude Desktop<br/>(the model runs here)"]

    subgraph SRV["MCP server"]
        direction TB
        S1["1 Validate against<br/>the catalogue"]
        S2["2 Compile the intent<br/>into SQL"]
        S3["3 Execute read-only,<br/>capped"]
        S4["4 Record receipt<br/>and trace"]
        S1 --> S2 --> S3 --> S4
    end

    CAT[/"Metric catalogue<br/>(YAML)"/]
    WH[("Warehouse<br/>(marts)")]
    LOG[/"Receipts + traces"/]

    U <-- "question / answer" --> AG
    AG -- "intent" --> S1
    CAT -- "definitions" --> S1
    S3 <-- "SQL / rows" --> WH
    S4 -- "receipt, trace" --> LOG
    S4 -- "rows + definition +<br/>label + receipt ID" --> AG

    classDef governed fill:#dcfce7,stroke:#22a05a,color:#111
    classDef person fill:#dbeafe,stroke:#3b82f6,color:#111
    class CAT governed
    class U person
```

| Step | What happens | Why |
|---|---|---|
| Validate | Metric, dimensions, grain and filter operators must be values the catalogue allows. Personal-data columns are in no list, so they cannot be named | Bad requests fail early, with the valid options in the error |
| Compile | Relative periods such as "last quarter" become absolute dates against a recorded as-of date. Dimensions and filters are sorted, values are escaped, and the output is byte-identical for the same intent | Two phrasings of one question give one query, and "last quarter" means the same thing on replay |
| Execute | A short read-only connection to the marts, with file and network access switched off, capped in rows and time | Least privilege |
| Record | The receipt is written before the result is returned; the trace covers failures too | Every number can be checked later |

## Where the data comes from

```mermaid
flowchart LR
    GEN["Seeded generator<br/>synthetic marketplace data,<br/>with deliberate traps"]
    RAW[("raw schema<br/>orders, refunds, commissions,<br/>listings, dealers")]
    FX[/"FX rates<br/>(dbt seed)"/]
    STG["staging<br/>clean, deduplicate"]
    INT["intermediate<br/>refunds and commission per order,<br/>listing status as date ranges"]
    MARTS[("marts schema<br/>fct_orders, fct_listings,<br/>dim_dealers")]
    TESTS{{"dbt tests<br/>keys, relationships, ranges,<br/>recompute from raw"}}

    GEN --> RAW
    GEN --> FX
    RAW --> STG
    FX --> STG
    STG --> INT --> MARTS
    TESTS -. "checks" .-> STG
    TESTS -. "checks" .-> MARTS
    MARTS -- "the only schema<br/>metrics may read" --> SRV["MCP server"]
```

In production, this half belongs to BI: the marts come from their existing dbt project, and the server reads them through a read-only role from IT.

## Checking and learning from it afterwards

```mermaid
flowchart LR
    REC[/"receipts.jsonl"/]
    TR[/"traces.jsonl"/]
    WH[("marts")]

    REC -- "receipt ID" --> RP["Replay command (BI)<br/>rerun the stored SQL"]
    WH --> RP
    RP --> OK{"Result hash<br/>matches?"}
    OK -- "yes" --> SAME["Same number, confirmed"]
    OK -- "no" --> DIFF["Data changed since:<br/>compare data snapshots"]

    TR --> Q["Trace queries in DuckDB"]
    Q --> KPI["Rollout measures<br/>certified share, error rate, latency"]
    Q --> PROM["Promotion candidates<br/>most-repeated exploratory questions"]
    PROM --> BI["BI certifies a new metric"]

    GOLD[/"Golden questions<br/>answers from independent SQL"/] --> CI["CI on every push<br/>generator, dbt build,<br/>golden check, tests"]
    WH --> CI
```

## Hard and soft controls

| Control | Kind | Where |
|---|---|---|
| Read-only connection with no file or network access, marts only, row cap, timeout | Hard | Server |
| Free-form SQL only through `explore_sql`: one SELECT over the marts, no personal-data columns, always labelled exploratory | Hard | Allow-list and server |
| Only catalogue metrics, dimensions and filters can be requested | Hard | Tool schema and compiler |
| Certified or exploratory label set from the catalogue | Hard | Server |
| A receipt for every answer | Hard | Server |
| Asking which "revenue" is meant, and quoting the label and receipt | Soft | Tool guidance and the `governed-analytics` skill, checked by golden questions |

## Status (17 Nov 2026)

All parts shown here are built and tested. The open items are listed in the README under "Deliberately not built" and "Who it hands off to".
