"""Process-level tests for the GitHub App token helper used by agent workflows."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.integration

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
HELPER = REPOSITORY_ROOT / "scripts" / "github-app" / "github-app.ps1"
APP_ID = 123456
INSTALLATION_ID = 7890
FAKE_TOKEN = "ghs_test_installation_token"
SHA256_DIGEST_INFO = bytes.fromhex("3031300d060960864801650304020105000420")


@dataclass(frozen=True)
class RsaTestKey:
    pem_path: Path
    modulus: int
    exponent: int


@dataclass
class RecordedRequest:
    path: str
    headers: dict[str, str]
    body: dict[str, Any]


@dataclass
class FakeGitHubApi:
    base_url: str
    requests: list[RecordedRequest] = field(default_factory=list)


def _pwsh() -> str:
    executable = shutil.which("pwsh")
    if executable is None:
        pytest.fail("PowerShell 7 (pwsh) is required to test scripts/github-app/github-app.ps1")
    return executable


def _b64url_decode(segment: str) -> bytes:
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


@pytest.fixture(scope="module")
def rsa_key(tmp_path_factory: pytest.TempPathFactory) -> RsaTestKey:
    script = (
        "$r = [Security.Cryptography.RSA]::Create(2048); "
        "$p = $r.ExportParameters($false); "
        "@{ pem = $r.ExportRSAPrivateKeyPem(); "
        "n = [Convert]::ToBase64String($p.Modulus); "
        "e = [Convert]::ToBase64String($p.Exponent) } | ConvertTo-Json -Compress"
    )
    completed = subprocess.run(
        [_pwsh(), "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    generated = json.loads(completed.stdout)
    pem_path = tmp_path_factory.mktemp("key") / "app.pem"
    pem_path.write_text(generated["pem"], encoding="ascii")
    return RsaTestKey(
        pem_path=pem_path,
        modulus=int.from_bytes(base64.b64decode(generated["n"]), "big"),
        exponent=int.from_bytes(base64.b64decode(generated["e"]), "big"),
    )


@pytest.fixture
def fake_api() -> Iterator[FakeGitHubApi]:
    recorded: list[RecordedRequest] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
            recorded.append(
                RecordedRequest(path=self.path, headers=dict(self.headers.items()), body=body)
            )
            payload = json.dumps(
                {"token": FAKE_TOKEN, "expires_at": "2026-11-08T01:00:00Z"}
            ).encode()
            self.send_response(201)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield FakeGitHubApi(
            base_url=f"http://127.0.0.1:{server.server_address[1]}", requests=recorded
        )
    finally:
        server.shutdown()
        server.server_close()


def _write_config(tmp_path: Path, **overrides: object) -> Path:
    config_path = tmp_path / "app.json"
    config_path.write_text(json.dumps(overrides), encoding="utf-8")
    return config_path


def _base_config(rsa_key: RsaTestKey, fake_api: FakeGitHubApi) -> dict[str, object]:
    return {
        "appId": APP_ID,
        "installationId": INSTALLATION_ID,
        "privateKeyPath": str(rsa_key.pem_path),
        "repository": "keiba-ai",
        "apiBaseUrl": fake_api.base_url,
    }


def _run_helper(
    config_path: Path, *arguments: str, stdin: str = "", cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ, KEIBA_GITHUB_APP_CONFIG=str(config_path))
    return subprocess.run(
        [_pwsh(), "-NoProfile", "-File", str(HELPER), *arguments],
        input=stdin,
        capture_output=True,
        text=True,
        env=environment,
        cwd=cwd,
        timeout=120,
        check=False,
    )


def _assert_valid_app_jwt(authorization: str, rsa_key: RsaTestKey) -> None:
    scheme, _, jwt = authorization.partition(" ")
    assert scheme == "Bearer"
    header_segment, payload_segment, signature_segment = jwt.split(".")
    assert json.loads(_b64url_decode(header_segment)) == {"alg": "RS256", "typ": "JWT"}
    claims = json.loads(_b64url_decode(payload_segment))
    assert claims["iss"] == APP_ID
    assert 0 < claims["exp"] - claims["iat"] <= 600

    key_length = (rsa_key.modulus.bit_length() + 7) // 8
    digest = hashlib.sha256(f"{header_segment}.{payload_segment}".encode("ascii")).digest()
    digest_info = SHA256_DIGEST_INFO + digest
    expected = b"\x00\x01" + b"\xff" * (key_length - len(digest_info) - 3) + b"\x00" + digest_info
    signature = int.from_bytes(_b64url_decode(signature_segment), "big")
    recovered = pow(signature, rsa_key.exponent, rsa_key.modulus).to_bytes(key_length, "big")
    assert recovered == expected


def test_credential_get_returns_repository_scoped_installation_token(
    tmp_path: Path, rsa_key: RsaTestKey, fake_api: FakeGitHubApi
) -> None:
    config_path = _write_config(tmp_path, **_base_config(rsa_key, fake_api))

    completed = _run_helper(
        config_path, "credential", "get", stdin="protocol=https\nhost=github.com\n\n"
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == (
        f"protocol=https\nhost=github.com\nusername=x-access-token\npassword={FAKE_TOKEN}\n"
    )
    assert len(fake_api.requests) == 1
    request = fake_api.requests[0]
    assert request.path == f"/app/installations/{INSTALLATION_ID}/access_tokens"
    assert request.body == {"repositories": ["keiba-ai"]}
    _assert_valid_app_jwt(request.headers["Authorization"], rsa_key)


def test_credential_get_answers_nothing_for_other_hosts(
    tmp_path: Path, rsa_key: RsaTestKey, fake_api: FakeGitHubApi
) -> None:
    config_path = _write_config(tmp_path, **_base_config(rsa_key, fake_api))

    completed = _run_helper(
        config_path, "credential", "get", stdin="protocol=https\nhost=example.com\n\n"
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
    assert fake_api.requests == []


@pytest.mark.parametrize("operation", ["store", "erase"])
def test_credential_store_and_erase_are_noops(
    tmp_path: Path, rsa_key: RsaTestKey, fake_api: FakeGitHubApi, operation: str
) -> None:
    config_path = _write_config(tmp_path, **_base_config(rsa_key, fake_api))

    completed = _run_helper(
        config_path,
        "credential",
        operation,
        stdin=f"protocol=https\nhost=github.com\nusername=x-access-token\npassword={FAKE_TOKEN}\n\n",
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
    assert fake_api.requests == []


def test_gh_passes_token_only_to_the_child_process(
    tmp_path: Path, rsa_key: RsaTestKey, fake_api: FakeGitHubApi
) -> None:
    # The fake gh is the Python interpreter running a script literally named "pr",
    # so `gh pr view 12` executes that script with the remaining arguments.
    (tmp_path / "pr").write_text(
        "import os, sys\nprint(os.environ['GH_TOKEN'])\nprint(' '.join(sys.argv[1:]))\n",
        encoding="utf-8",
    )
    config_path = _write_config(tmp_path, **_base_config(rsa_key, fake_api), ghPath=sys.executable)

    completed = _run_helper(config_path, "gh", "pr", "view", "12", "--json", "state", cwd=tmp_path)

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.splitlines() == [FAKE_TOKEN, "view 12 --json state"]
    assert len(fake_api.requests) == 1


@pytest.mark.parametrize(
    "gh_arguments",
    [["pr", "merge", "12"], ["pr", "review", "12", "--approve"], ["api", "repos"], ["auth"]],
)
def test_gh_rejects_commands_outside_the_agent_allow_list(
    tmp_path: Path, rsa_key: RsaTestKey, fake_api: FakeGitHubApi, gh_arguments: list[str]
) -> None:
    config_path = _write_config(tmp_path, **_base_config(rsa_key, fake_api))

    completed = _run_helper(config_path, "gh", *gh_arguments)

    assert completed.returncode == 1
    assert "not allowed" in completed.stderr
    assert completed.stdout == ""
    assert fake_api.requests == []


def test_rejects_plain_http_api_outside_loopback(
    tmp_path: Path, rsa_key: RsaTestKey, fake_api: FakeGitHubApi
) -> None:
    config = _base_config(rsa_key, fake_api) | {"apiBaseUrl": "http://example.com"}
    config_path = _write_config(tmp_path, **config)

    completed = _run_helper(config_path, "check")

    assert completed.returncode == 1
    assert "https" in completed.stderr
    assert completed.stdout == ""


def test_missing_configuration_fails_without_output(tmp_path: Path) -> None:
    completed = _run_helper(
        tmp_path / "missing.json", "credential", "get", stdin="protocol=https\nhost=github.com\n\n"
    )

    assert completed.returncode == 1
    assert "configuration file not found" in completed.stderr
    assert completed.stdout == ""


def test_check_reports_success_without_printing_the_token(
    tmp_path: Path, rsa_key: RsaTestKey, fake_api: FakeGitHubApi
) -> None:
    config_path = _write_config(tmp_path, **_base_config(rsa_key, fake_api))

    completed = _run_helper(config_path, "check")

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.startswith(f"ok: installation {INSTALLATION_ID} repository keiba-ai")
    assert FAKE_TOKEN not in completed.stdout
