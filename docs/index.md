# pronresolve

`pronresolve` discovers pronunciation ambiguity from dictionary data and resolves a token only when contextual lexical evidence is strong enough. This guide describes installation, discovery, runtime use, the JSON index contract, and the CLI.

```{toctree}
:maxdepth: 2

api
```

## Installation

Install the published package with `python -m pip install pronresolve`. To build the documentation locally, install the docs extra with `python -m pip install -e ".[docs]"`.

## Concept

The package separates offline discovery from runtime resolution. Dictionary entries are grouped by normalized spelling and POS. Stable reading identifiers connect generated profiles to the pronunciation lexicon. The runtime loads a JSON index and scores exact normalized context-token overlap; it does not access dictionary services.

## Discovery pipeline

Call `discover_ambiguities(entries, language="en", locale="en-US")` with a reusable iterable or streaming iterator of mapping- or object-shaped entries. Entries with missing/empty POS are excluded from automatic resolution and reported in `DiscoveryReport.entries_without_pos`. Missing pronunciation is counted separately. If one source entry contains multiple distinct IPA values, its senses cannot safely be linked to an individual IPA, so the key is reported as unlinked rather than guessed.

## Runtime resolution

Use `Resolver.from_path(index_path)` and `resolve(text, start, end, pos=..., lemma=...)`. Offsets refer to the original sentence's character positions. The resolver returns a `Resolution` or `None`; abstention is intentional when the word is unknown, cues are absent, the best score is too weak, or the top candidates are too close. If it abstains, keep the existing default pronunciation behavior.

`resolve_token()` accepts mappings and spaCy-like token objects. POS and lemma are optional; if POS is omitted where the index has multiple POS groups, resolution abstains.

## Conservative abstention rules

The default score and margin thresholds are heuristic. Context matching ignores generic stopwords, uses closest repeated-term distance, and takes the strongest matching field weight. Evidence from antonyms currently contributes positively as related-term evidence; it does not subtract from a candidate score. No linguistic certainty is claimed.

## JSON index format

Schema version 1 requires root fields `schema_version` (integer `1`), `language` (non-empty string), `locale` (string or null), and `profiles` (array). Each profile requires non-empty string `word`, `pos`, and `reading_id`, and a non-empty array of non-empty IPA strings. Optional evidence arrays contain strings. Unknown fields are ignored; unsupported schema versions and malformed values are rejected. Dataset/version metadata belongs to the containing data package/artifact rather than the index JSON.

## CLI

`pronresolve build --input-jsonl entries.jsonl --output index.json --language en` builds the index and a sibling `.report.json` file. `pronresolve inspect index.json` and `pronresolve validate index.json` print a summary. Invalid user input returns exit code 2 with a concise stderr error and no traceback.

## Integration boundary

Generate the index beside the matching pronunciation lexicon using correctly filtered source data. The producer owns locale selection and dataset/version metadata. A consuming frontend supplies sentence text, token offsets, and available POS/lemma data, then applies a returned `READING:<reading_id>` selector through its existing lookup path.

## Limitations

- No morphological lemmatization; resolution uses exact normalized tokens.
- No runtime locale filtering.
- No automatic sense-to-IPA assignment for multi-IPA source entries.
- Missing/empty POS entries are skipped and reported.
- Heuristic thresholds favor abstention with weak or close evidence.

## API reference

See the {doc}`api` page for the public objects exported by `pronresolve`.
