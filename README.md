# pronresolve

`pronresolve` discovers same-spelling, same-part-of-speech pronunciation ambiguity from dictionary data and chooses a reading from sentence context only when evidence is strong enough. It is an alpha, data-driven MVP: there is no word-specific heteronym table and no runtime dependency on Lexhint, G2Lex, or Lexphon.

## Install

```bash
python -m pip install pronresolve
```

For development and documentation:

```bash
python -m pip install -e ".[dev,docs]"
python -m pytest
python -m sphinx -W --keep-going -b html docs docs/_build/html
```

Versions are derived from Git tags with `setuptools-scm`. Source archives without Git metadata use the configured development fallback version.
The current CI matrix verifies Python 3.10–3.13; Python 3.14 has not yet been added to the supported/tested release matrix.

## Concept and discovery

### Optional build-time pronunciation equivalence

Exact normalized IPA comparison remains the default. Pronunciation values with no segment-like Unicode letter (including punctuation-only placeholders such as `…`) are rejected unconditionally; this screening is not a full IPA validator.

Install the optional structural comparator only when building with phonodist equivalence:

```bash
python -m pip install "pronresolve[phonetic]"
pronresolve build --input-jsonl german.jsonl --output de.json --language de \\
  --pronunciation-equivalence phonodist --stress-policy all \\
  --strict-equivalence --audit-output de-equivalence-audit.json
```

Phonodist mode compares structure rather than treating a zero feature distance as identity. `all` preserves primary and secondary stress (the default); `primary` may ignore secondary stress. Discovery merges only safe pairwise-equivalent cliques; comparator errors and non-transitive components remain unresolved. Resolution IDs are semantic `r2` IDs and do not depend on IPA.

The sibling `.report.json` records pronunciation, equivalence, semantic-anchor, and contrastive-cue outcomes, including structured unresolved reasons. `--strict-equivalence` aborts if comparisons fail. The optional audit is a separate, sorted build-only file. Phonodist remains optional; runtime consumers use deterministic schema v3 without it.
Discovery groups by normalized `(word, POS)`, safely partitions pronunciation equivalence classes, merges evidence within each class, and creates `r2` IDs from explicit semantic anchors rather than IPA or cues. Missing or overlapping anchors are unresolved. A curated anchor overlay may supply reviewed semantic keys when stable source sense IDs are absent.

```python
from pronresolve import discover_ambiguities, save_index

result = discover_ambiguities(lexicon.iter_entries(), language="en", locale="en-US")
save_index(result.index, "en-us.pronresolve.json")
print(result.report.as_dict())
```

A same-word/POS group with one final pronunciation-equivalence class is not a runtime ambiguity. Groups with multiple classes are emitted only when they have safe semantic anchors and contrastive cues; entries with missing POS are excluded and counted. Multiple IPA values on a source entry without safe sense linkage are unresolved rather than guessed.

## Runtime resolution

Load the generated file and provide original sentence text and target character offsets. POS and lemma are useful when the caller has them:

```python
from pronresolve import Resolver

resolver = Resolver.from_path("en-us.pronresolve.json")
decision = resolver.resolve(
    text="The archer picked up the bow and an arrow.",
    start=25,
    end=28,
    pos="NOUN",
    lemma="bow",
)
if decision is not None:
    selector = decision.selector
    anchor_ipa = decision.anchor_ipa
```

A `None` result means the existing default pronunciation path should remain in use. The resolver is deterministic and explainable, not a claim of linguistic certainty.

## CLI

```bash
pronresolve --help
pronresolve build --input-jsonl entries.jsonl --output index.json --language en --locale en-US
pronresolve inspect index.json [--word WORD]
pronresolve validate index.json
```

`build` reads JSONL and writes schema v3 plus `<output>.report.json`. `--rules-id` sets the shared ruleset identifier; `--curated-anchors` loads a reviewed JSON overlay, and `--identity-audit-output` writes semantic provenance separately. `inspect` shows IDs, diagnostic anchor IPA, and cues. `validate` accepts v1, v2, and v3; legacy IDs are never reidentified on load.

## What pronresolve stores

The runtime index is compact and contains resolution-class IDs, deterministic `anchor_ipa` representatives, and normalized cue tokens grouped by weight. It does not contain semantic anchors, sense IDs, or raw dictionary prose; discovery identity provenance belongs in build/audit records.

### Policy B runtime scoring

| Evidence field | Weight |
| -------------- | -----: |
| Synonyms       |    3.5 |
| Glosses        |    3.0 |
| Topics         |    2.5 |
| Tags           |    1.0 |
| Antonyms       |   0.75 |

Examples are excluded from runtime scoring and serialized cues. They are disproportionately large, can contain incidental words unrelated to sense identity, and are unnecessary for compact lexical matching; they may still be retained privately as build/audit evidence. Repeated cue tokens keep their maximum field weight rather than adding weights. Antonyms retain positive-association behavior for parity; signed or removed antonym evidence is deferred.

### Schema compatibility

New builds write schema v3 with `id_version: 2`. The loader accepts schema v1 and v2 during migration; v1 is compiled to the legacy schema-v2 runtime model, and v2 load/save remains schema v2 unless explicitly requested. Neither path changes old IDs. An explicit v3 write requires valid `r2` IDs.

`ReadingProfile.anchor_ipa` is the deterministic diagnostic representative, not the target lexicon pronunciation. `ReadingProfile.ipa` and `Resolution.ipa` remain compatibility aliases; use `anchor_ipa` in new integrations. Schema v3 does not store source sense IDs or semantic anchors in the runtime artifact.

Schema-v3 JSON includes `schema_version`, `id_version`, `rules_id`, `language`, `locale`, and `entries` grouped as `word -> POS -> candidates`. Each candidate stores `id`, diagnostic `anchor_ipa`, and `cues`. The ID represents a semantic pronunciation-resolution class; target assets must bind it to their own native pronunciation values and must not compare them with `anchor_ipa`.

## Integration boundary

The producer supplies source data and locale-specific shared rules. Consumers pass token offsets/context to the resolver, then bind `READING:<r2-id>` to target-native pronunciation values. Never compare target values with `anchor_ipa` or regenerate IDs from target encodings.

## Limitations

- No morphological lemmatization: matching uses exact normalized context tokens.
- No runtime locale filtering; prepare correctly filtered locale-specific indexes upstream.
- No automatic sense-to-IPA linking when one source entry has multiple IPA values.
- Entries without POS are skipped by discovery and counted in its report.
- Resolver thresholds are heuristic defaults; conservative abstention is expected when context is weak or scores are close.
- Antonyms currently count as positive related-term evidence, not negative evidence.

## Documentation

The full user guide and public API reference are in the [Sphinx documentation](docs/index.md). Build with `python -m pip install -e ".[docs]"` followed by `python -m sphinx -W --keep-going -b html docs docs/_build/html`.

## License

Apache License, Version 2.0. See [LICENSE](LICENSE).
