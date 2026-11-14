# GR-01: Data access is read-only

- **ID:** GR-01
- **Requirement:** The server MUST open the warehouse with a read-only connection. Tools MUST NOT be able to create, change or delete data, schemas or files.
- **Rationale:** An assistant that writes SQL can write any SQL. Checking statements is a second line of defence; the first is a connection that cannot write at all.
- **Owner:** IT (warehouse roles). Until handover: kit maintainer.
- **Enforced by:** Read-only database connection (in production, a read-only warehouse role); statement checks in [GR-02](GR-02-query-allow-list.md) as a second layer.
- **How to verify:** `pytest -m gr01` sends `INSERT`, `UPDATE`, `DELETE`, `CREATE`, `DROP`, `ATTACH` and `COPY … TO` through every tool and asserts each is rejected, then asserts the database file's checksum is unchanged.
