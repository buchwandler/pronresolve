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

The build pipeline streams dictionary-entry mappings or objects into `discover_ambiguities()`. The package groups by normalized spelling and POS, normalizes pronunciations, and generates stable reading IDs.

```python
from pronresolve import discover_ambiguities, save_index

result = discover_ambiguities(lexicon.iter_entries(), language="en", locale="en-US")
save_index(result.index, "en-us.pronresolve.json")
print(result.report.as_dict())
```

A key with only one IPA is not ambiguous. Multiple IPA values on one source entry are treated as unlinked ambiguity and omitted rather than guessed. Entries with missing or empty POS are excluded from automatic resolution and counted in `entries_without_pos` in the discovery report. Missing pronunciation is also counted separately.

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
    ipa = decision.ipa
```

A `None` result means the existing default pronunciation path should remain in use. The resolver is deterministic and explainable, not a claim of linguistic certainty.

## CLI

```bash
pronresolve --help
pronresolve build --input-jsonl entries.jsonl --output index.json --language en --locale en-US
pronresolve inspect index.json [--word WORD]
pronresolve validate index.json
```

`build` reads one JSON object per non-empty JSONL line and writes a compact v2 index plus `<output>.report.json`. `inspect` prints summary counts; add `--word WORD` to view each reading's IPA, sense IDs, and weighted cues. `validate` accepts v1 and v2. Invalid input or an invalid index returns exit code `2` and writes a concise `pronresolve: error: ...` message to stderr.

## What pronresolve stores

The resolver index is a compact decision artifact, not a copy of dictionary records. Schema v2 groups candidates by normalized word and POS. Each runtime reading profile contains a reading ID, scalar IPA, sense IDs, and normalized cue tokens grouped by weight. Raw gloss, synonym, topic, tag, antonym, example, and etymology prose is not stored in runtime profiles.

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

New indexes are written as compact, deterministic schema v2 JSON. The loader also accepts schema v1, compiles its synonyms, glosses, topics, tags, and antonyms into Policy B cues, and deliberately ignores examples and etymology numbers for runtime resolution. Therefore v1 scores are not guaranteed to match the previous resolver when examples contributed evidence.

The runtime `ReadingProfile` API intentionally changed: IPA is scalar and lexical evidence is exposed as compiled `Cue` values instead of raw prose fields. `Resolution.ipa` is also scalar. Callers should use the returned `sense_ids`, `evidence_terms`, and reading ID for runtime explanation and selection.

Schema-v2 JSON uses `schema_version`, `language`, `locale`, and an `entries` object grouped as `word -> POS -> candidates`; each candidate stores `id`, scalar `ipa`, optional `sense_ids`, and `cues` grouped by weight. Unsupported versions and malformed structures are rejected. Dataset/version identity belongs to the containing lexicon package or artifact metadata, not the index JSON; publish the index beside its matching pronunciation lexicon.

## Integration boundary

The producer supplies dictionary entries and locale-filtered source data. Consumers load the generated index, pass token spans/context to the resolver, and apply the returned `READING:<reading_id>` selector through their existing selector-aware lookup. Locale is stored as metadata only; runtime locale filtering is not performed here.

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
