---
schema_version: 2
object_type: release_entry
versioning:
  schema_version: 1
  revision: 1
entry_id: entry-0001
release_version: v0.1.1
kind: changed
summary: Changed runtime indexes to use schema v2 with precompiled weighted cues
status: accepted
audience: null
scopes: []
source_refs:
  - git:5471e6db76347e73d0759c45242cd6ebdef11b1f
paths:
  - README.md
  - docs/index.md
  - pronresolve/__init__.py
  - pronresolve/cli.py
  - pronresolve/compile.py
  - pronresolve/discovery.py
  - pronresolve/models.py
  - pronresolve/normalization.py
  - pronresolve/resolver.py
  - pronresolve/storage.py
  - tests/test_cli.py
  - tests/test_compilation.py
  - tests/test_discovery.py
  - tests/test_models.py
  - tests/test_resolver.py
  - tests/test_schema_v2.py
  - tests/test_storage.py
issues: []
prs: []
sources:
  - git:5471e6db76347e73d0759c45242cd6ebdef11b1f
contributors:
  - "@holgern"
breaking: true
internal: false
order: 1
---

Runtime profiles now expose scalar IPA, sense IDs, and normalized weighted cues instead of retaining raw dictionary evidence. Schema-v1 indexes remain loadable through the compatibility decoder, while the CLI can inspect readings and cues for a selected word.
