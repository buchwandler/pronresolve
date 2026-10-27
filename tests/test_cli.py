import json
import subprocess
import sys

import pytest

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
    summary = json.loads(output.out)
    assert summary["resolvable_keys"] == 1
    assert index_path.exists()
    report = tmp_path / "index.json.report.json"
    assert json.loads(report.read_text(encoding="utf-8"))["entries_scanned"] == 2
    assert main(["inspect", str(index_path)]) == 0
    assert json.loads(capsys.readouterr().out)["valid"] is True
    assert main(["validate", str(index_path)]) == 0


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
