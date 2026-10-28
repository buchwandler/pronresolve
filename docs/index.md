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

The package separates offline discovery from runtime resolution. Discovery groups by normalized `(word, POS)`, safely links senses, partitions spoken-equivalent pronunciations, constructs semantic resolution classes, and compiles contrastive weighted cues. Schema-v3 `r2` IDs identify those classes independently of IPA; runtime scoring remains deterministic and dependency-light.

## Discovery pipeline

## Optional build-time pronunciation equivalence

`discover_ambiguities()` and `pronresolve build` use exact normalized IPA identity by default. Invalid pronunciation values with no segment-like Unicode letter are rejected independently of this option; this is a minimal placeholder screen, not full IPA validation.

For conservative structural comparison, install the optional dependency and select phonodist explicitly:

```bash
python -m pip install "pronresolve[phonetic]"
pronresolve build --input-jsonl german.jsonl --output de.json --language de \\
  --pronunciation-equivalence phonodist --stress-policy all \\
  --strict-equivalence --audit-output de-equivalence-audit.json
```

The `all` stress policy preserves primary and secondary stress. `primary` may ignore secondary stress, but never primary stress. Discovery merges only safe pairwise-equivalent cliques; comparator errors and non-transitive components are unresolved. IDs are semantic `r2` values, and only explicit structural equivalence rules may merge pronunciations.

The build report records pronunciation, equivalence, semantic-anchor, and contrastive-cue outcomes with structured unresolved reasons. `--strict-equivalence` fails on comparison errors. `--audit-output` writes separate sorted build-only details. Phonodist remains optional; runtime consumers use dependency-free schema v3.
Call `discover_ambiguities(entries, language="en", locale="en-US")` with mapping- or object-shaped entries. Discovery resolves only same-word/POS ambiguities. Missing POS and pronunciation are reported; multiple pronunciations on one source entry remain unlinked unless explicit safe linkage exists. Every emitted class needs a disjoint stable semantic anchor (source sense IDs or an explicit curated overlay); glosses, cues, and IPA never become identity.

## Runtime resolution

Use `Resolver.from_path(index_path)` and `resolve(text, start, end, pos=..., lemma=...)`. Offsets refer to original sentence character positions. The resolver scores normalized context tokens against precompiled contrastive cues and returns a `Resolution` or `None`. Matched cue tokens, the semantic reading ID, and the anchor IPA provide runtime diagnostics without storing dictionary prose or semantic provenance. Abstention is intentional when the word is unknown, cues are absent, the best score is too weak, or the top candidates are too close.

`resolve_token()` accepts mappings and spaCy-like token objects. POS and lemma are optional; if POS is omitted where the index has multiple POS groups, resolution abstains.

## Conservative abstention rules

The default score and margin thresholds are heuristic. Context matching ignores generic stopwords, uses closest repeated-term distance, and takes the strongest matching field weight. Evidence from antonyms currently contributes positively as related-term evidence; it does not subtract from a candidate score. No linguistic certainty is claimed.

## JSON index format

## What the runtime stores

The compact schema-v3 artifact groups candidates as `word -> POS -> readings`; each candidate stores a semantic `r2` ID, diagnostic `anchor_ipa`, and cues grouped by weight. It deliberately omits sense IDs, semantic anchors, and raw dictionary prose; provenance belongs in build/audit records.

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

New builds write schema v3 with `id_version: 2`. The loader accepts v1 and v2 during migration; v1 becomes a schema-v2 runtime model after cue compilation, while v2 load/save stays schema v2 unless explicitly requested. Neither loader reidentifies old IDs; an explicit v3 write requires valid `r2` IDs.

## CLI

`pronresolve build --input-jsonl entries.jsonl --output index.json --language en` writes schema v3 and a sibling `.report.json`; `--rules-id` sets a shared ruleset identifier, `--curated-anchors` loads reviewed anchor data, and `--identity-audit-output` keeps provenance separate. `inspect` shows IDs, diagnostic anchor IPA, and cues. `validate` accepts v1, v2, and v3.

## Integration boundary

Build rules from correctly filtered locale data. A consuming frontend supplies context and applies the returned `READING:<reading_id>` selector through its existing lookup. Target assets bind `r2` IDs to their native values; `anchor_ipa` is diagnostic and is not a target pronunciation constraint.

## Limitations

- No morphological lemmatization; resolution uses exact normalized tokens.
- No runtime locale filtering.
- No automatic sense-to-IPA assignment for multi-IPA source entries.
- Missing/empty POS entries are skipped and reported.
- Heuristic thresholds favor abstention with weak or close evidence.

## API reference

See the {doc}`api` page for the public objects exported by `pronresolve`.
