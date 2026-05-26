"""
The conformance harness must pass against the reference implementation
it is shipped alongside. If it ever fails here, either the harness or
the implementation has drifted.
"""

from telaro_ars.conformance import run_self_test, as_json


def test_run_self_test_passes_against_reference():
    report = run_self_test()
    assert report.ok, "\n" + report.summary()


def test_state_vectors_have_terminal_states_or_explicit():
    report = run_self_test()
    assert report.state_passed >= 5
    assert report.illegal_passed >= 3
    assert report.view_bond_passed >= 4


def test_as_json_is_serialisable_and_complete():
    blob = as_json()
    assert blob["profile"] == "ARS-Solana Profile v0.1"
    assert len(blob["state_vectors"]) >= 5
    assert len(blob["illegal_vectors"]) >= 3
    assert len(blob["view_bond_vectors"]) >= 4
    # Make sure each state vector preserves the event type discriminator
    for v in blob["state_vectors"]:
        for e in v["log"]:
            assert "type" in e
