---
schema_version: 2
object_type: release_entry
versioning:
  schema_version: 1
  revision: 1
entry_id: entry-0002
release_version: v0.1.0
kind: changed
summary:
  Changed discovery and index output for determinism, added strict data validation,
  and expanded documentation
status: accepted
audience: null
scopes: []
source_refs:
  - git:3743632dbd82c9cd302e63ee09a596e2267030d2
paths:
  - pronresolve/discovery.py
  - pronresolve/models.py
  - pronresolve/cli.py
  - pyproject.toml
  - README.md
  - docs/index.md
  - docs/api.md
  - docs/make.py
  - tests/test_cli.py
  - tests/test_discovery.py
  - tests/test_models.py
  - tests/test_normalization.py
  - tests/test_resolver.py
issues: []
prs: []
sources:
  - git:3743632dbd82c9cd302e63ee09a596e2267030d2
contributors:
  - "@holgern"
breaking: false
internal: false
order: 2
---
