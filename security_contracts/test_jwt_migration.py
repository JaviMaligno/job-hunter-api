"""Synthetic JWT migration contracts: no app lifespan, providers or real database."""

import asyncio
import base64
import hashlib
import hmac
import importlib
import json
import os
import socket
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import Engine
from sqlalchemy.ext.asyncio import AsyncEngine

REPO = "job"
SUBJECT = "123" if REPO == "prompt" else "00000000-0000-0000-0000-000000000001"
KIND = "type" if REPO == "job" else "typ" if REPO == "prompt" else None
ALGORITHMS = ("HS256",) if REPO == "book" else ("HS256", "HS384", "HS512", "RS256", "ES256")
SECRET = "synthetic-jwt-migration-key-only-" + "x" * 48


def _segment(value):
    return base64.urlsafe_b64encode(json.dumps(value, separators=(",", ":")).encode()).rstrip(b"=")


def _signed(payload, key=SECRET, algorithm="HS256"):
    message = _segment({"alg": algorithm, "typ": "JWT"}) + b"." + _segment(payload)
    key = key.encode() if isinstance(key, str) else key
    digest = hmac.new(key, message, getattr(hashlib, "sha" + algorithm[2:])).digest()
    return (message + b"." + base64.urlsafe_b64encode(digest).rstrip(b"=")).decode()


def _claims(**overrides):
    payload = {"sub": SUBJECT, "role": "reader"}
    if KIND:
        payload[KIND] = "access"
    return {**payload, **overrides}


def _rejected(auth, token):
    if REPO == "job":
        with pytest.raises(auth.module.TokenError):
            auth.module.verify_token(token)
    else:
        assert auth.module.verify_token(token) is None


@pytest.fixture
def auth(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("JWT contracts must not access network, providers or database")

    # Expose only synthetic settings to application imports; never inspect ambient credentials.
    monkeypatch.setattr(os, "environ", {})
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setenv("SECRET_KEY", SECRET)
    monkeypatch.setenv("ALGORITHM", "HS256")
    monkeypatch.setenv(
        "DATABASE_URL", "sqlite:///:memory:" if REPO != "job" else "sqlite+aiosqlite:///:memory:"
    )
    monkeypatch.setenv("ENVIRONMENT", "testing")
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("BEDROCK_ENABLED", "false")
    for name in (
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
    ):
        monkeypatch.setenv(name, "")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    for owner, name in (
        (httpx.HTTPTransport, "handle_request"),
        (httpx.AsyncHTTPTransport, "handle_async_request"),
        (socket, "getaddrinfo"),
        (socket, "create_connection"),
        (Engine, "connect"),
        (AsyncEngine, "connect"),
    ):
        monkeypatch.setattr(owner, name, forbidden)
    try:
        from pydantic_settings.sources import DotEnvSettingsSource
    except ImportError:
        pass  # Book's auth module uses only the explicitly overridden environment.
    else:
        monkeypatch.setattr(DotEnvSettingsSource, "_read_env_files", lambda self: {})
    if REPO == "job":
        import anthropic

        monkeypatch.setattr(anthropic.Anthropic, "__init__", forbidden)
        monkeypatch.setattr(anthropic.AnthropicBedrock, "__init__", forbidden)
        from src.auth import jwt as module
    elif REPO == "prompt":
        from backend.services import auth as module
    else:
        from server import auth as module

    def configure(key, algorithm="HS256"):
        if REPO == "book":
            assert algorithm == "HS256"
            monkeypatch.setattr(module, "get_secret_key", lambda: key)
        else:
            monkeypatch.setattr(
                module.settings, "jwt_secret_key" if REPO == "job" else "secret_key", key
            )
            monkeypatch.setattr(
                module.settings, "jwt_algorithm" if REPO == "job" else "algorithm", algorithm
            )

    configure(SECRET)
    return SimpleNamespace(module=module, configure=configure)


@pytest.fixture
def legacy():
    return json.loads(Path(__file__).with_name("jwt_legacy_tokens.json").read_text())


@pytest.mark.parametrize("algorithm", ALGORITHMS)
def test_legacy_tokens_remain_accepted(auth, legacy, algorithm):
    row = legacy["algorithms"][algorithm]
    auth.configure(row["key"], algorithm)
    verified = auth.module.verify_token(row["token"])
    assert verified == SUBJECT if REPO == "book" else verified == row["payload"]
    if REPO == "job":
        assert auth.module.verify_token(row["refresh_token"], "refresh")["type"] == "refresh"
        _rejected(auth, row["refresh_token"])
    elif REPO == "prompt":
        assert auth.module.verify_refresh_token(row["refresh_token"])["typ"] == "refresh"
        assert auth.module.verify_refresh_token(row["token"]) is None


def _issue_access(auth):
    if REPO == "book":
        return auth.module.create_access_token(SUBJECT)
    if REPO == "job":
        return auth.module.create_access_token(
            UUID(SUBJECT), "synthetic@example.invalid", {"role": "reader"}
        )
    return auth.module.create_access_token({"sub": SUBJECT, "role": "reader"})


@pytest.mark.parametrize("algorithm", ALGORITHMS)
def test_new_tokens_preserve_configured_algorithm_and_claims(auth, algorithm):
    private = public = SECRET
    if algorithm in ("RS256", "ES256"):
        key = (
            rsa.generate_private_key(public_exponent=65537, key_size=2048)
            if algorithm == "RS256"
            else ec.generate_private_key(ec.SECP256R1())
        )
        private = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        public = key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    auth.configure(private, algorithm)
    token = _issue_access(auth)
    assert isinstance(token, str)
    auth.configure(public, algorithm)
    payload = auth.module.verify_token(token)
    if REPO == "book":
        assert payload == SUBJECT
    else:
        assert payload["sub"] == SUBJECT
        assert payload[KIND] == "access"
        assert payload["role"] == "reader"


@pytest.mark.skipif(REPO == "book", reason="Book has no refresh-token API")
def test_refresh_wire_and_hash_contract(auth):
    if REPO == "job":
        token, digest, expiry = auth.module.create_refresh_token(UUID(SUBJECT))
        assert digest == hashlib.sha256(token.encode()).hexdigest() == auth.module.hash_token(token)
        assert expiry.tzinfo is not None
        assert auth.module.verify_token(token, "refresh")["type"] == "refresh"
        _rejected(auth, token)
    else:
        token = auth.module.create_refresh_token({"sub": SUBJECT, "role": "reader"})
        assert auth.module.verify_refresh_token(token)["typ"] == "refresh"
        assert auth.module.verify_refresh_token(_issue_access(auth)) is None


@pytest.mark.parametrize(
    "claim",
    [
        {"aud": []},
        {"aud": ""},
        {"aud": None},
        {"aud": "foreign"},
        {"at_hash": ""},
        {"at_hash": None},
        {"at_hash": "synthetic"},
        {"iat": "invalid"},
        {"exp": 1},
        {"exp": None},
        {"nbf": 4102444800},
        {"sub": 123},
        {"jti": 123},
    ],
)
def test_invalid_claims_remain_rejected(auth, claim):
    _rejected(auth, _signed(_claims(**claim)))


def test_wrong_signature_and_algorithm_remain_rejected(auth):
    _rejected(auth, _signed(_claims(), key="different-synthetic-key"))
    _rejected(auth, _signed(_claims(), algorithm="HS512"))
    unsigned = (_segment({"alg": "none"}) + b"." + _segment(_claims()) + b".").decode()
    _rejected(auth, unsigned)


def test_der_hmac_confusion_is_rejected(auth, legacy):
    # DER bytes are public material, never an acceptable symmetric signing secret.
    # Book's fixed HS256 policy still must reject a misconfigured public key.
    if "RS256" in legacy["algorithms"]:
        der = base64.b64decode(legacy["algorithms"]["RS256"]["public_der_base64"])
    else:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        der = key.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    auth.configure(der)
    _rejected(auth, _signed(_claims(), key=der))


def test_future_iat_security_hardening(auth):
    _rejected(auth, _signed(_claims(iat=int(datetime.now(UTC).timestamp()) + 3600)))


def test_expiry_equal_now_security_hardening(auth, monkeypatch):
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2035, 1, 1, tzinfo=tz)

    decoder = (
        auth.module.jwt
        if auth.module.jwt.__name__ == "jose.jwt"
        else importlib.import_module("jwt.api_jwt")
    )
    monkeypatch.setattr(decoder, "datetime", FixedDateTime)
    _rejected(auth, _signed(_claims(exp=int(FixedDateTime.now(UTC).timestamp()))))


def test_invalid_token_keeps_http_error_family_before_database_lookup(auth):
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer", credentials=_signed(_claims(), key="wrong-key")
    )
    database = MagicMock()
    with pytest.raises(HTTPException) as error:
        if REPO == "book":
            from server.deps import get_current_user

            get_current_user(credentials, database)
        elif REPO == "job":
            from src.api.dependencies import get_current_user

            asyncio.run(get_current_user(credentials, database))
        else:
            from backend.api.auth import get_current_user

            asyncio.run(get_current_user(credentials, database))
    assert error.value.status_code == 401
    if REPO != "book":
        assert error.value.headers == {"WWW-Authenticate": "Bearer"}
    database.exec.assert_not_called()
    database.execute.assert_not_called()


def test_signed_role_claim_does_not_replace_database_principal(auth):
    from unittest.mock import AsyncMock

    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer", credentials=_signed(_claims(role="admin"))
    )
    database = MagicMock()
    trusted = SimpleNamespace(id=SUBJECT, role="free", tier="free")
    if REPO == "book":
        from server.deps import get_current_user

        database.exec.return_value.first.return_value = trusted
        actual = get_current_user(credentials, database)
    elif REPO == "job":
        from src.api.dependencies import get_current_user

        result = MagicMock()
        result.scalar_one_or_none.return_value = trusted
        database.execute = AsyncMock(return_value=result)
        actual = asyncio.run(get_current_user(credentials, database))
    else:
        from backend.api.auth import get_current_user

        database.exec.return_value.first.return_value = trusted
        actual = asyncio.run(get_current_user(credentials, database))
    assert actual is trusted
    assert actual.role == "free"
    assert actual.tier == "free"


@pytest.mark.parametrize("verification_format", ["private-pem", "certificate-pem"])
def test_rsa_verification_preserves_existing_configured_key_formats(auth, verification_format):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    auth.configure(private, "RS256")
    token = _issue_access(auth)
    if verification_format == "certificate-pem":
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "synthetic.invalid")])
        certificate = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(subject)
            .public_key(key.public_key())
            .serial_number(1)
            .not_valid_before(datetime(2020, 1, 1, tzinfo=UTC))
            .not_valid_after(datetime(2100, 1, 1, tzinfo=UTC))
            .sign(key, hashes.SHA256())
        )
        auth.configure(certificate.public_bytes(serialization.Encoding.PEM), "RS256")
    assert auth.module.verify_token(token)["sub"] == SUBJECT


@pytest.mark.parametrize(
    "key", [b"-----BEGIN CERTIFICATE-----\ninvalid", b"-----BEGIN PRIVATE KEY-----\ninvalid"]
)
def test_malformed_rsa_configuration_stays_in_token_error_family(auth, legacy, key):
    auth.configure(key, "RS256")
    _rejected(auth, legacy["algorithms"]["RS256"]["token"])
