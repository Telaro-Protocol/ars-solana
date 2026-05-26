"""
CLI tests for `telaro-conformance`. Tests the self-test mode + the
python: transport against the reference itself. HTTP transport is
covered by integration tests in a separate runner because it needs
a live endpoint.
"""

import json
import subprocess
import sys

import pytest

from telaro_ars.conformance_cli import (
    _certificate_from_report,
    _fingerprint,
    main,
)
from telaro_ars.conformance import run_self_test


def test_certificate_from_report_passes_when_reference_passes():
    report = run_self_test()
    cert = _certificate_from_report(
        report, subject="test-subject", transport="self-test"
    )
    assert cert.passed
    assert cert.profile_version == "v0.1"
    assert cert.signature is None  # not signed unless --sign-with passed


def test_fingerprint_is_stable_for_same_inputs():
    report = run_self_test()
    fp1 = _fingerprint(report, "subject-a", 1700000000)
    fp2 = _fingerprint(report, "subject-a", 1700000000)
    assert fp1 == fp2


def test_fingerprint_changes_with_subject_or_time():
    report = run_self_test()
    fp_a = _fingerprint(report, "subject-a", 1700000000)
    fp_b = _fingerprint(report, "subject-b", 1700000000)
    fp_c = _fingerprint(report, "subject-a", 1700000001)
    assert fp_a != fp_b
    assert fp_a != fp_c


def test_self_test_mode_passes(capsys):
    rc = main(["self-test"])
    assert rc == 0


def test_self_test_with_cert_outputs_json(capsys):
    rc = main(["self-test", "--cert"])
    assert rc == 0
    out = capsys.readouterr().out
    cert = json.loads(out)
    assert cert["profile"] == "ARS-Solana"
    assert cert["state_passed"] == cert["state_total"]


def test_run_python_transport_against_reference(capsys):
    rc = main(["run", "--against", "python:telaro_ars"])
    assert rc == 0
    out = capsys.readouterr().out
    cert = json.loads(out)
    assert cert["transport"] == "python"
    assert cert["subject"] == "python:telaro_ars"
    assert cert["state_passed"] == cert["state_total"]


def test_run_rejects_bad_transport_spec():
    rc = main(["run", "--against", "ftp://nope"])
    assert rc == 2


def test_dump_vectors_outputs_corpus(capsys):
    rc = main(["dump-vectors"])
    assert rc == 0
    out = capsys.readouterr().out
    blob = json.loads(out)
    assert blob["profile"] == "ARS-Solana Profile v0.1"
    assert len(blob["state_vectors"]) >= 5
    assert len(blob["illegal_vectors"]) >= 3
    assert len(blob["view_bond_vectors"]) >= 4


def test_console_entry_point_is_installed():
    """The pyproject `[project.scripts]` entry should install a
    `telaro-conformance` script on PATH."""
    result = subprocess.run(
        [sys.executable, "-m", "telaro_ars.conformance_cli", "self-test"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "State vectors" in result.stderr
