import json
import subprocess
import sys

import pytest

from pronresolve import discover_ambiguities, save_index
from pronresolve.cli import main


def _run_cli(capsys, args):
    status = main(args)
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err
    return status, captured


def _entry(ipa, gloss):
    return {
        "word": "lead",
        "pos": "NOUN",
        "pronunciations": [{"ipa": ipa}],
        "senses": [{"sense_id": gloss, "glosses": [gloss]}],
    }


def test_build_inspect_validate_cli(tmp_path, capsys):
    source = tmp_path / "entries.jsonl"
    source.write_text(
        "\n".join(
            json.dumps(_entry(ipa, gloss)) for ipa, gloss in (("liːd", "metal"), ("lɛd", "guide"))
        )
        + "\n",
        encoding="utf-8",
    )
    index_path = tmp_path / "index.json"
    status, output = _run_cli(
        capsys,
        ["build", "--input-jsonl", str(source), "--output", str(index_path), "--language", "en"],
    )
    assert status == 0
    assert json.loads(output.out)["schema_version"] == 2
    assert json.loads(output.out)["resolvable_keys"] == 1
    assert index_path.exists()
    assert json.loads(index_path.read_text(encoding="utf-8"))["schema_version"] == 2
    report = tmp_path / "index.json.report.json"
    assert json.loads(report.read_text(encoding="utf-8"))["entries_scanned"] == 2

    assert main(["inspect", str(index_path)]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["valid"] is True
    assert summary["ambiguous_word_count"] == 1
    assert summary["word_pos_group_count"] == 1
    assert summary["profile_count"] == 2
    assert summary["cue_count"] == 2
    assert summary["average_cues_per_profile"] == 1.0

    assert main(["inspect", str(index_path), "--word", "LEAD"]) == 0
    details = json.loads(capsys.readouterr().out)
    assert details["word"] == "lead"
    assert len(details["readings"]) == 2
    assert {reading["pos"] for reading in details["readings"]} == {"NOUN"}
    assert {reading["ipa"] for reading in details["readings"]} == {"liːd", "lɛd"}
    assert all(reading["sense_ids"] for reading in details["readings"])
    assert all(reading["weighted_cues"] for reading in details["readings"])

    assert main(["validate", str(index_path)]) == 0
    assert json.loads(capsys.readouterr().out)["schema_version"] == 2


def test_validate_and_inspect_accept_v1_and_show_policy_b_runtime(tmp_path, capsys):
    legacy = {
        "schema_version": 1,
        "language": "en",
        "locale": "en-US",
        "profiles": [
            {
                "word": "read",
                "pos": "VERB",
                "reading_id": "r1",
                "ipa": ["ɹiːd"],
                "sense_ids": ["s1"],
                "glosses": ["comprehend"],
                "examples": ["exampleonlycue"],
                "synonyms": ["interpret"],
            },
            {
                "word": "read",
                "pos": "VERB",
                "reading_id": "r2",
                "ipa": ["ɹɛd"],
                "sense_ids": ["s2"],
                "glosses": ["past"],
            },
        ],
    }
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps(legacy), encoding="utf-8")

    assert main(["validate", str(path)]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["schema_version"] == 1
    assert summary["runtime_schema_version"] == 2

    assert main(["inspect", str(path), "--word", "read"]) == 0
    details = json.loads(capsys.readouterr().out)
    assert details["schema_version"] == 1
    assert details["runtime_schema_version"] == 2
    cues = [
        token
        for reading in details["readings"]
        for tokens in reading["weighted_cues"].values()
        for token in tokens
    ]
    assert "comprehend" in cues
    assert "interpret" in cues
    assert "exampleonlycue" not in cues


def test_policy_b_v2_serialization_is_at_most_half_equivalent_v1_pretty_fixture(tmp_path):
    examples = [f"Example {number}: " + "incidentalword " * 10 for number in range(20)]
    rows = [_entry("liːd", "metal"), _entry("lɛd", "guide")]
    for row in rows:
        row["senses"][0]["examples"] = examples
    index = discover_ambiguities(rows, language="en", locale="en-US").index
    sense_by_id = {row["senses"][0]["sense_id"]: row["senses"][0] for row in rows}
    legacy_profiles = []
    for profile in index.profiles:
        sense = sense_by_id[profile.sense_ids[0]]
        legacy_profiles.append(
            {
                "word": profile.word,
                "pos": profile.pos,
                "reading_id": profile.reading_id,
                "ipa": [profile.ipa],
                "sense_ids": list(profile.sense_ids),
                "etymology_numbers": ["1"],
                "glosses": sense["glosses"],
                "topics": [],
                "tags": [],
                "examples": sense["examples"],
                "synonyms": [],
                "antonyms": [],
            }
        )
    legacy_pretty = json.dumps(
        {
            "schema_version": 1,
            "language": "en",
            "locale": "en-US",
            "profiles": legacy_profiles,
        },
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8")
    v2_path = save_index(index, tmp_path / "compact.json")
    assert v2_path.stat().st_size <= 0.5 * len(legacy_pretty)


@pytest.mark.parametrize(
    "contents",
    ["{bad json}\n", "[]\n"],
)
def test_build_rejects_invalid_jsonl(tmp_path, capsys, contents):
    source = tmp_path / "bad.jsonl"
    source.write_text(contents, encoding="utf-8")
    status, output = _run_cli(
        capsys,
        [
            "build",
            "--input-jsonl",
            str(source),
            "--output",
            str(tmp_path / "index.json"),
            "--language",
            "en",
        ],
    )
    assert status == 2
    assert output.err.startswith("pronresolve: error:")


def test_build_rejects_missing_jsonl(tmp_path, capsys):
    status, output = _run_cli(
        capsys,
        [
            "build",
            "--input-jsonl",
            str(tmp_path / "absent"),
            "--output",
            str(tmp_path / "index.json"),
            "--language",
            "en",
        ],
    )
    assert status == 2
    assert output.err.startswith("pronresolve: error:")


@pytest.mark.parametrize(
    "contents",
    [
        "{bad json",
        "123",
        json.dumps({"schema_version": 99, "language": "en", "locale": None, "profiles": []}),
        json.dumps({"schema_version": 1, "language": "en", "locale": None, "profiles": [123]}),
    ],
)
def test_validate_rejects_malformed_indexes(tmp_path, capsys, contents):
    path = tmp_path / "bad.json"
    path.write_text(contents, encoding="utf-8")
    status, output = _run_cli(capsys, ["validate", str(path)])
    assert status == 2
    assert output.err.startswith("pronresolve: error:")


def test_module_help_smoke():
    result = subprocess.run(
        [sys.executable, "-m", "pronresolve", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "usage: pronresolve" in result.stdout.lower()


def test_build_phonodist_writes_structural_audit_and_report(tmp_path, capsys, monkeypatch):
    from types import SimpleNamespace

    import pronresolve.cli as cli

    created = {}

    class FakePhonodistEquivalence:
        def __init__(self, *, language, stress_policy):
            created["configuration"] = (language, stress_policy)

        def evaluate(self, left, right):
            comparison = SimpleNamespace(
                segmental=SimpleNamespace(distance=0.05, operations=()),
                classification="segmental",
                stress_operations=(),
            )
            return False, comparison

    monkeypatch.setattr(cli, "PhonodistEquivalence", FakePhonodistEquivalence)
    source = tmp_path / "entries.jsonl"
    source.write_text(
        "\n".join(json.dumps(_entry(ipa, ipa)) for ipa in ("liːd", "lɛd")) + "\n",
        encoding="utf-8",
    )
    output_path = tmp_path / "index.json"
    audit_path = tmp_path / "audit.json"

    status, output = _run_cli(
        capsys,
        [
            "build",
            "--input-jsonl",
            str(source),
            "--output",
            str(output_path),
            "--language",
            "de-DE",
            "--pronunciation-equivalence",
            "phonodist",
            "--stress-policy",
            "primary",
            "--audit-output",
            str(audit_path),
        ],
    )

    assert status == 0
    assert created["configuration"] == ("de-DE", "primary")
    assert len(json.loads(output.out)["equivalence_audit"]) > 0
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert audit[0]["classification"] == "segmental"
    assert audit[0]["distance"] == 0.05
    report = json.loads((tmp_path / "index.json.report.json").read_text(encoding="utf-8"))
    assert report["equivalence_comparisons"] == 1


def test_strict_phonodist_build_records_errors_and_fails_without_index(
    tmp_path, capsys, monkeypatch
):
    import pronresolve.cli as cli

    class BrokenPhonodistEquivalence:
        def __init__(self, *, language, stress_policy):
            pass

        def evaluate(self, left, right):
            raise ValueError("unsupported segment")

        def equivalent(self, left, right):
            raise ValueError("unsupported segment")

    monkeypatch.setattr(cli, "PhonodistEquivalence", BrokenPhonodistEquivalence)
    source = tmp_path / "entries.jsonl"
    source.write_text(
        "\n".join(json.dumps(_entry(ipa, ipa)) for ipa in ("liːd", "lɛd")) + "\n",
        encoding="utf-8",
    )
    output_path = tmp_path / "index.json"

    status, output = _run_cli(
        capsys,
        [
            "build",
            "--input-jsonl",
            str(source),
            "--output",
            str(output_path),
            "--language",
            "de-DE",
            "--pronunciation-equivalence",
            "phonodist",
            "--strict-equivalence",
        ],
    )

    assert status == 2
    assert "comparison errors occurred: 1" in output.err
    assert not output_path.exists()
    report = json.loads((tmp_path / "index.json.report.json").read_text(encoding="utf-8"))
    assert report["equivalence_errors"] == 1


def test_audit_output_requires_phonodist_mode(tmp_path, capsys):
    status, output = _run_cli(
        capsys,
        [
            "build",
            "--input-jsonl",
            str(tmp_path / "absent.jsonl"),
            "--output",
            str(tmp_path / "index.json"),
            "--language",
            "en",
            "--audit-output",
            str(tmp_path / "audit.json"),
        ],
    )

    assert status == 2
    assert "requires --pronunciation-equivalence phonodist" in output.err
