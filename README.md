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
pronresolve inspect index.json
pronresolve validate index.json
```

`build` reads one JSON object per non-empty JSONL line and writes an index plus `<output>.report.json`. `inspect` and `validate` print a summary. Invalid input or an invalid index returns exit code `2` and writes a concise `pronresolve: error: ...` message to stderr.

## JSON index schema

Schema version 1 is a JSON object with required root fields:

- `schema_version`: integer exactly `1`;
- `language`: non-empty string;
- `locale`: string or `null`;
- `profiles`: array of profile objects.

Every profile requires non-empty string `word`, `pos`, and `reading_id`, plus a non-empty `ipa` array of non-empty strings. Optional evidence arrays (`sense_ids`, `etymology_numbers`, `glosses`, `topics`, `tags`, `examples`, `synonyms`, `antonyms`) contain strings. Unknown fields are ignored for forward-compatible readers; unsupported schema versions are rejected. Malformed structures are rejected rather than coerced.

Dataset/version identity belongs to the containing lexicon data package or artifact metadata, not to the v1 index JSON. Publish the index alongside the matching pronunciation lexicon and keep their dataset versions aligned.

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
