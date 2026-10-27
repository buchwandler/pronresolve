# pronresolve

`pronresolve` discovers pronunciation ambiguity from dictionary data and resolves a token only when contextual lexical evidence is strong enough. This guide describes installation, discovery, runtime use, the JSON index contract, and the CLI.

```{toctree}
:maxdepth: 2

api
changelog
```

## Installation

Install the published package with `python -m pip install pronresolve`. To build the documentation locally, install the docs extra with `python -m pip install -e ".[docs]"`.

## Concept

The package separates offline discovery from runtime resolution. Discovery safely links readings to source senses, then compiles useful evidence into normalized weighted cues. Schema-v2 indexes group candidates by normalized word and POS; runtime resolution matches sentence tokens directly against precompiled cues without dictionary-service access or repeated profile tokenization.

## Discovery pipeline

Call `discover_ambiguities(entries, language="en", locale="en-US")` with a reusable iterable or streaming iterator of mapping- or object-shaped entries. Entries with missing/empty POS are excluded from automatic resolution and reported in `DiscoveryReport.entries_without_pos`. Missing pronunciation is counted separately. If one source entry contains multiple distinct IPA values, its senses cannot safely be linked to an individual IPA, so the key is reported as unlinked rather than guessed.

## Runtime resolution

Use `Resolver.from_path(index_path)` and `resolve(text, start, end, pos=..., lemma=...)`. Offsets refer to original sentence character positions. The resolver scores normalized context tokens against precompiled weighted cues and returns a `Resolution` or `None`. Matched cue tokens and sense IDs provide runtime explanation without retaining dictionary prose. Abstention is intentional when the word is unknown, cues are absent, the best score is too weak, or the top candidates are too close.

`resolve_token()` accepts mappings and spaCy-like token objects. POS and lemma are optional; if POS is omitted where the index has multiple POS groups, resolution abstains.

## Conservative abstention rules

The default score and margin thresholds are heuristic. Context matching ignores generic stopwords, uses closest repeated-term distance, and takes the strongest matching field weight. Evidence from antonyms currently contributes positively as related-term evidence; it does not subtract from a candidate score. No linguistic certainty is claimed.

## JSON index format

## What the runtime stores

The compact v2 runtime index is a decision artifact, not a dictionary-record copy. It groups candidates as `word -> POS -> readings`; each reading stores an ID, scalar IPA, optional sense IDs, and cues grouped by weight. Raw glosses, synonyms, topics, tags, antonyms, examples, and etymology numbers are not retained in runtime profiles.

## Policy B scoring

| Evidence field | Weight |
| -------------- | -----: |
| Synonyms       |    3.5 |
| Glosses        |    3.0 |
| Topics         |    2.5 |
| Tags           |    1.0 |
| Antonyms       |   0.75 |

Examples are excluded from compiled cues, the runtime index, and scoring. They are disproportionately large and often contain incidental words unrelated to sense identity; private discovery/build evidence may retain them for audit purposes. Duplicate tokens use the maximum field weight, not a sum. Antonyms intentionally retain positive-association behavior at 0.75; signed/removal semantics are deferred.

## Schema compatibility

New indexes are written as compact deterministic schema v2 JSON. The loader accepts both v1 and v2; loading v1 compiles synonyms, glosses, topics, tags, and antonyms into Policy B cues, ignores examples and etymology numbers for runtime, preserves sense IDs, and normalizes a validated one-pronunciation IPA array to scalar IPA. This intentionally does not guarantee legacy v1 score parity when examples affected the old resolver. The runtime `ReadingProfile` and `Resolution.ipa` shapes intentionally use scalar IPA and compiled cues instead of raw evidence prose.

## CLI

`pronresolve build --input-jsonl entries.jsonl --output index.json --language en` writes a compact v2 index and sibling `.report.json`. `pronresolve inspect index.json` prints summary counts; add `--word WORD` to see readings, scalar IPA, sense IDs, and weighted cues. `pronresolve validate index.json` accepts v1 and v2. Invalid user input returns exit code 2 with a concise stderr error and no traceback.

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
