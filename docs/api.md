# API reference

The following objects are exported from the top-level `pronresolve` package.

```{eval-rst}
.. automodule:: pronresolve
   :members:
   :undoc-members:
```

## Build-time equivalence policies

The top-level package exports `PronunciationEquivalence`, `ExactEquivalence`, `PhonodistEquivalence`, and `EquivalenceConfigurationError`. Exact comparison is the default discovery behavior; pass an explicit `PhonodistEquivalence(language=..., stress_policy="all"|"primary")` to enable structural filtering. Constructing that optional policy loads phonodist and requires the `phonetic` extra. It is not needed by index loaders or runtime resolution.

`DiscoveryReport.as_dict()` includes invalid-pronunciation, equivalence-comparison, comparison-error, and suppressed-equivalent-key counters. `DiscoveryResult.equivalence_audit` contains the optional build-only audit records. These additions do not alter schema-v2 index serialization or runtime dependencies.
