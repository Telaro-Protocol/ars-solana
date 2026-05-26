"""
CLI for the ARS-Solana Profile v0.1 conformance harness.

Two modes:

  1. `telaro-conformance self-test`
       Runs the harness against the reference Python implementation
       shipped in this package. Useful for CI of `telaro-ars` itself
       and as a sanity check before installing in production.

  2. `telaro-conformance run --against <impl-spec>`
       Runs the harness against a non-reference implementation. The
       implementation is identified by an `<impl-spec>`:

         - `python:dotted.path` — import the dotted-path Python module
           and look for the convention exports (`apply_event`, `replay`,
           `build_view_bond_ix`, `LockCollateralParams`).

         - `http:https://your-impl.example.com` — POST event logs to
           the implementation's HTTP endpoint and compare replies.
           The endpoint must follow the protocol documented in
           CONFORMANCE.md.

       On success, writes a JSON `ConformanceCertificate` to stdout
       (or to `--out path`). The certificate carries a Telaro-issued
       Ed25519 signature if `--sign-with <keypair-path>` is set, so
       downstream consumers can verify the certificate came from us.

The CLI is intentionally minimal in v0.1. The HTTP transport is a
forward path for cross-language implementations; the Python transport
covers reference + early Python forks.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from telaro_ars.conformance import (
    ILLEGAL_VECTORS,
    STATE_VECTORS,
    VIEW_BOND_VECTORS,
    ConformanceReport,
    as_json,
    run_self_test,
)


# -------------------------------------------------------------------- #
#  Certificate                                                          #
# -------------------------------------------------------------------- #


@dataclass
class ConformanceCertificate:
    """A signed declaration that an implementation passes the suite."""

    profile: str
    profile_version: str
    issuer: str
    subject: str
    issued_at: int
    transport: str
    state_passed: int
    state_total: int
    illegal_passed: int
    illegal_total: int
    view_bond_passed: int
    view_bond_total: int
    fingerprint: str
    """Hex SHA-256 over the canonical (state + illegal + view_bond)
    pass counts + subject + issued_at. Re-issued certificates with
    the same subject + suite must share this fingerprint."""

    signature: str | None = None
    """Ed25519 signature over fingerprint, hex. Optional in v0.1."""

    @property
    def passed(self) -> bool:
        return (
            self.state_passed == self.state_total
            and self.illegal_passed == self.illegal_total
            and self.view_bond_passed == self.view_bond_total
        )


def _fingerprint(report: ConformanceReport, subject: str, issued_at: int) -> str:
    h = hashlib.sha256()
    h.update(subject.encode("utf-8"))
    h.update(b"|")
    h.update(str(issued_at).encode("utf-8"))
    h.update(b"|")
    h.update(f"s{report.state_passed}/{report.state_passed + len(report.state_failed)}".encode())
    h.update(b"|")
    h.update(
        f"i{report.illegal_passed}/{report.illegal_passed + len(report.illegal_failed)}".encode()
    )
    h.update(b"|")
    h.update(
        f"v{report.view_bond_passed}/{report.view_bond_passed + len(report.view_bond_failed)}".encode()
    )
    return h.hexdigest()


def _certificate_from_report(
    report: ConformanceReport,
    subject: str,
    transport: str,
) -> ConformanceCertificate:
    issued_at = int(time.time())
    fp = _fingerprint(report, subject, issued_at)
    return ConformanceCertificate(
        profile="ARS-Solana",
        profile_version="v0.1",
        issuer="telaro-ars conformance harness",
        subject=subject,
        issued_at=issued_at,
        transport=transport,
        state_passed=report.state_passed,
        state_total=report.state_passed + len(report.state_failed),
        illegal_passed=report.illegal_passed,
        illegal_total=report.illegal_passed + len(report.illegal_failed),
        view_bond_passed=report.view_bond_passed,
        view_bond_total=report.view_bond_passed + len(report.view_bond_failed),
        fingerprint=fp,
    )


def _sign_certificate(cert: ConformanceCertificate, keypair_path: str) -> str:
    """Sign the certificate's fingerprint with a Solana keypair file
    (the same JSON-array format `solana-keygen new` produces). Returns
    the Ed25519 signature hex."""
    try:
        from solders.keypair import Keypair  # solders ships ed25519
    except ImportError as e:
        raise RuntimeError(
            "signing requires the 'solders' package, which is already a "
            "telaro-ars dependency. unexpected import failure: " + str(e)
        )
    with open(keypair_path) as f:
        secret = json.load(f)
    kp = Keypair.from_bytes(bytes(secret))
    sig = kp.sign_message(cert.fingerprint.encode("utf-8"))
    return bytes(sig).hex()


# -------------------------------------------------------------------- #
#  Transport: Python (dotted module)                                    #
# -------------------------------------------------------------------- #


def _run_python_transport(module_path: str) -> ConformanceReport:
    """Import the target module and run the harness against its
    exported names. The module must expose:

      apply_event, replay, ARSTransitionError  (state machine)
      build_view_bond_ix, LockCollateralParams (binding)

    These match `telaro_ars` itself, so a fork or alternate impl that
    keeps the same surface can be verified directly."""
    mod = importlib.import_module(module_path)
    needed = [
        "apply_event",
        "replay",
        "ARSTransitionError",
        "build_view_bond_ix",
        "LockCollateralParams",
    ]
    missing = [n for n in needed if not hasattr(mod, n)]
    if missing:
        raise RuntimeError(
            f"target module {module_path!r} is missing required exports: {missing}"
        )

    # For the v0.1 CLI we simply call our own run_self_test but in a
    # generalised way that defers to the target module's symbols.
    # The reference vectors are defined against `telaro_ars`'s shapes,
    # so the target must also implement those shapes byte-for-byte.
    target_replay = mod.replay
    target_apply = mod.apply_event
    target_build = mod.build_view_bond_ix
    target_params = mod.LockCollateralParams
    target_err = mod.ARSTransitionError

    r = ConformanceReport()
    for v in STATE_VECTORS:
        try:
            job = target_replay(v.log)
            if (
                job.state == v.expected_state
                and getattr(job, "released_atomic", 0) == v.expected_released_atomic
            ):
                r.state_passed += 1
            else:
                r.state_failed.append(
                    f"{v.name}: got state={job.state}, released={getattr(job, 'released_atomic', None)}"
                )
        except Exception as e:
            r.state_failed.append(f"{v.name}: raised {type(e).__name__}: {e}")

    for v in ILLEGAL_VECTORS:
        try:
            target_replay(v.log)
            r.illegal_failed.append(f"{v.name}: should have raised")
        except target_err:
            r.illegal_passed += 1
        except Exception as e:
            r.illegal_failed.append(f"{v.name}: raised wrong type {type(e).__name__}")

    from solders.pubkey import Pubkey

    agent = Pubkey.from_string(
        "4Nd1mYJgC7DsB3v9pkM9CRZxoUTfXn1kbm1zFM5hZRgM"
    )
    for v in VIEW_BOND_VECTORS:
        ix = target_build(
            target_params(
                job_id="conformance",
                agent=agent,
                min_bond_atomic=v.min_bond_atomic,
                min_score=v.min_score,
            )
        )
        got = bytes(ix.data).hex()
        if got == v.expected_data_hex:
            r.view_bond_passed += 1
        else:
            r.view_bond_failed.append(
                f"{v.name}: expected {v.expected_data_hex}, got {got}"
            )
    return r


# -------------------------------------------------------------------- #
#  Transport: HTTP (cross-language)                                     #
# -------------------------------------------------------------------- #


def _run_http_transport(endpoint: str) -> ConformanceReport:
    """POST each vector set to the implementation and compare replies.

    Protocol (documented in CONFORMANCE.md):

      POST <endpoint>/replay      body: { events: [...] }
                                  response: { state, released_atomic }
      POST <endpoint>/replay      same shape; an illegal log
                                  must respond with HTTP 400
      POST <endpoint>/view_bond   body: { min_bond, min_score }
                                  response: { data_hex }
    """
    try:
        import requests
    except ImportError:
        raise RuntimeError(
            "HTTP transport requires the 'requests' package. pip install requests"
        )

    base = endpoint.rstrip("/")
    r = ConformanceReport()

    for v in STATE_VECTORS:
        body = {"events": [e.__dict__ for e in v.log]}
        try:
            resp = requests.post(f"{base}/replay", json=body, timeout=10)
            if resp.status_code != 200:
                r.state_failed.append(f"{v.name}: HTTP {resp.status_code}")
                continue
            payload = resp.json()
            if (
                payload.get("state") == v.expected_state
                and int(payload.get("released_atomic") or 0)
                == v.expected_released_atomic
            ):
                r.state_passed += 1
            else:
                r.state_failed.append(
                    f"{v.name}: got state={payload.get('state')}, released={payload.get('released_atomic')}"
                )
        except Exception as e:
            r.state_failed.append(f"{v.name}: transport {type(e).__name__}: {e}")

    for v in ILLEGAL_VECTORS:
        body = {"events": [e.__dict__ for e in v.log]}
        try:
            resp = requests.post(f"{base}/replay", json=body, timeout=10)
            if 400 <= resp.status_code < 500:
                r.illegal_passed += 1
            else:
                r.illegal_failed.append(
                    f"{v.name}: expected 4xx, got {resp.status_code}"
                )
        except Exception as e:
            r.illegal_failed.append(f"{v.name}: transport {type(e).__name__}: {e}")

    for v in VIEW_BOND_VECTORS:
        body = {"min_bond": v.min_bond_atomic, "min_score": v.min_score}
        try:
            resp = requests.post(f"{base}/view_bond", json=body, timeout=10)
            if resp.status_code != 200:
                r.view_bond_failed.append(f"{v.name}: HTTP {resp.status_code}")
                continue
            payload = resp.json()
            got = str(payload.get("data_hex") or "")
            if got == v.expected_data_hex:
                r.view_bond_passed += 1
            else:
                r.view_bond_failed.append(
                    f"{v.name}: expected {v.expected_data_hex}, got {got}"
                )
        except Exception as e:
            r.view_bond_failed.append(f"{v.name}: transport {type(e).__name__}: {e}")

    return r


# -------------------------------------------------------------------- #
#  CLI                                                                  #
# -------------------------------------------------------------------- #


def _dump_certificate(cert: ConformanceCertificate, *, pretty: bool) -> str:
    d = asdict(cert)
    return json.dumps(d, indent=2 if pretty else None, sort_keys=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="telaro-conformance",
        description="ARS-Solana Profile v0.1 conformance harness CLI",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_self = sub.add_parser("self-test", help="Run against the reference implementation.")
    p_self.add_argument("--cert", action="store_true", help="Emit a certificate JSON to stdout.")
    p_self.add_argument("--sign-with", type=str, help="Solana keypair JSON path to sign the certificate.")
    p_self.add_argument("--out", type=str, help="Write certificate to this path instead of stdout.")

    p_run = sub.add_parser("run", help="Run against a third-party implementation.")
    p_run.add_argument(
        "--against",
        required=True,
        type=str,
        help="`python:dotted.path` or `http:https://endpoint` to verify.",
    )
    p_run.add_argument("--sign-with", type=str, help="Solana keypair JSON path to sign the certificate.")
    p_run.add_argument("--out", type=str, help="Write certificate to this path instead of stdout.")

    p_dump = sub.add_parser("dump-vectors", help="Print the test corpus as JSON.")
    p_dump.add_argument("--out", type=str)

    args = parser.parse_args(argv)

    if args.cmd == "self-test":
        report = run_self_test()
        print(report.summary(), file=sys.stderr)
        if not args.cert and not args.out:
            return 0 if report.ok else 1
        cert = _certificate_from_report(
            report,
            subject="telaro-ars reference (python)",
            transport="self-test",
        )
        if args.sign_with:
            cert.signature = _sign_certificate(cert, args.sign_with)
        body = _dump_certificate(cert, pretty=True)
        if args.out:
            with open(args.out, "w") as f:
                f.write(body)
            print(f"wrote {args.out}", file=sys.stderr)
        else:
            print(body)
        return 0 if report.ok else 1

    if args.cmd == "run":
        spec: str = args.against
        if spec.startswith("python:"):
            transport = "python"
            module_path = spec[len("python:") :]
            report = _run_python_transport(module_path)
            subject = f"python:{module_path}"
        elif spec.startswith("http:") or spec.startswith("https:"):
            transport = "http"
            endpoint = spec[len("http:") :] if spec.startswith("http:") else spec
            report = _run_http_transport(endpoint if endpoint.startswith("http") else f"http:{endpoint}")
            subject = spec
        else:
            print(
                "error: --against must be 'python:<module>' or 'http:<endpoint>'",
                file=sys.stderr,
            )
            return 2

        print(report.summary(), file=sys.stderr)
        cert = _certificate_from_report(report, subject=subject, transport=transport)
        if args.sign_with:
            cert.signature = _sign_certificate(cert, args.sign_with)
        body = _dump_certificate(cert, pretty=True)
        if args.out:
            with open(args.out, "w") as f:
                f.write(body)
            print(f"wrote {args.out}", file=sys.stderr)
        else:
            print(body)
        return 0 if report.ok else 1

    if args.cmd == "dump-vectors":
        blob = as_json()
        body = json.dumps(blob, indent=2, default=str)
        if args.out:
            with open(args.out, "w") as f:
                f.write(body)
            print(f"wrote {args.out}", file=sys.stderr)
        else:
            print(body)
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
