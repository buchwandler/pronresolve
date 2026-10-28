# API reference

The following objects are exported from the top-level `pronresolve` package.

```{eval-rst}
.. automodule:: pronresolve
   :members:
   :undoc-members:
```

## Build-time equivalence policies

The top-level package exports `PronunciationEquivalence`, `ExactEquivalence`, `PhonodistEquivalence`, and `EquivalenceConfigurationError`. Exact comparison is the default discovery behavior; pass an explicit `PhonodistEquivalence(language=..., stress_policy="all"|"primary")` to enable structural filtering. Constructing that optional policy loads phonodist and requires the `phonetic` extra. It is not needed by index loaders or runtime resolution.

`DiscoveryReport.as_dict()` includes pronunciation, equivalence, semantic-anchor, contrastive-cue, and unresolved-reason metrics. `DiscoveryResult.equivalence_audit` and `identity_audit` contain build-only provenance. Schema-v3 runtime JSON remains dependency-light. The top-level package also exports `SemanticAnchor`, `SemanticIdentity`, `UnresolvedAmbiguity`, `reading_id_v2`, the partition API, and explicit v2/v3 codecs.
