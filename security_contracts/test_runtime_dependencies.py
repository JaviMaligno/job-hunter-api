"""Synthetic offline compatibility: no main app, providers or persistent data."""

import asyncio
import base64
import hashlib
import hmac
import json
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import bcrypt
import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, Request


def _public_der_hmac_token(claims, public_der):
    """Construct an attack token without asking a hardened signer to accept DER."""

    def segment(value):
        return base64.urlsafe_b64encode(json.dumps(value, separators=(",", ":")).encode()).rstrip(
            b"="
        )

    signed = segment({"alg": "HS256", "typ": "JWT"}) + b"." + segment(claims)
    signature = hmac.new(public_der, signed, hashlib.sha256).digest()
    return (signed + b"." + base64.urlsafe_b64encode(signature).rstrip(b"=")).decode()


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    import socket

    def refuse_network(*args, **kwargs):
        raise AssertionError("Security contracts must not open network connections")

    async def refuse_async_network(*args, **kwargs):
        refuse_network()

    # ASGITransport is deliberately allowed; real HTTP transports are not.
    # Do not intercept Windows asyncio's internal socketpair implementation.
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse_network)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", refuse_async_network)
    monkeypatch.setattr(socket, "getaddrinfo", refuse_network)
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING", "false")
    monkeypatch.setenv("LANGSMITH_API_KEY", "")
    monkeypatch.setenv("LANGCHAIN_API_KEY", "")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")


@pytest.fixture
def tokens(monkeypatch):
    from src.auth import jwt as tokens

    monkeypatch.setattr(tokens.settings, "jwt_secret_key", "synthetic-contract-key-only")
    monkeypatch.setattr(tokens.settings, "jwt_algorithm", "HS256")
    return tokens


def test_existing_hs256_access_refresh_and_hash_contract(tokens):
    user = UUID("00000000-0000-0000-0000-000000000001")
    access = tokens.create_access_token(user, "synthetic@example.com")
    refresh, digest, expiry = tokens.create_refresh_token(user)
    assert tokens.verify_token(access)["sub"] == str(user)
    assert tokens.verify_token(access)["email"] == "synthetic@example.com"
    assert tokens.verify_token(refresh, "refresh")["type"] == "refresh"
    assert digest == tokens.hash_token(refresh)
    assert expiry.tzinfo is not None
    with pytest.raises(tokens.TokenError):
        tokens.verify_token(refresh)


def test_hmac_algorithm_and_signature_mismatch_remain_rejected(tokens):
    claims = {"sub": "synthetic-user", "type": "access"}
    for key, algorithm in [(tokens.settings.jwt_secret_key, "HS512"), ("wrong-key", "HS256")]:
        token = jwt.encode(claims, key, algorithm=algorithm)
        with pytest.raises(tokens.TokenError):
            tokens.verify_token(token)


def test_configured_rsa_pem_and_der_hmac_confusion(tokens, monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    public = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    der = key.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    claims = {"sub": "synthetic-user", "type": "access"}
    valid = jwt.encode(claims, private, algorithm="RS256")
    attack = _public_der_hmac_token(claims, der)
    monkeypatch.setattr(tokens.settings, "jwt_algorithm", "RS256")
    monkeypatch.setattr(tokens.settings, "jwt_secret_key", public)
    assert tokens.verify_token(valid)["sub"] == "synthetic-user"
    with pytest.raises(tokens.TokenError):
        tokens.verify_token(attack)


def test_existing_bcrypt_hash_and_new_hash_roundtrip():
    from src.auth.password import hash_password, verify_password

    legacy = bcrypt.hashpw(b"synthetic-password", bcrypt.gensalt(rounds=4)).decode()
    assert verify_password("synthetic-password", legacy)
    assert not verify_password("wrong-password", legacy)
    assert verify_password("synthetic-password", hash_password("synthetic-password"))


def test_real_auth_router_login_preserves_response_and_token_contract(tokens):
    from src.api.routes.auth import router
    from src.db.session import get_db

    user = SimpleNamespace(
        id=UUID("00000000-0000-0000-0000-000000000001"),
        email="synthetic@example.com",
        password_hash=bcrypt.hashpw(b"synthetic-password", bcrypt.gensalt(rounds=4)).decode(),
    )
    db = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: user)),
        add=lambda value: None,
    )

    async def fake_db():
        yield db

    app = FastAPI()
    app.include_router(router, prefix="/auth")
    app.dependency_overrides[get_db] = fake_db

    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            good = await client.post(
                "/auth/login", json={"email": user.email, "password": "synthetic-password"}
            )
            bad = await client.post(
                "/auth/login", json={"email": user.email, "password": "wrong-password"}
            )
        return good, bad

    good, bad = asyncio.run(exercise())
    assert good.status_code == 200
    payload = good.json()
    assert payload["token_type"] == "bearer"
    assert payload["user"] == {"id": str(user.id), "email": user.email}
    assert tokens.verify_token(payload["access_token"])["sub"] == str(user.id)
    assert tokens.verify_token(payload["refresh_token"], "refresh")["sub"] == str(user.id)
    assert bad.status_code == 401


def test_urlencoded_field_limit_is_enforced():
    app = FastAPI()

    @app.post("/form")
    async def form(request: Request):
        async with request.form(max_fields=1) as data:
            return {"keys": list(data)}

    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            good = await client.post(
                "/form",
                content="a=1",
                headers={"content-type": "application/x-www-form-urlencoded"},
            )
            bad = await client.post(
                "/form",
                content="a=1&b=2",
                headers={"content-type": "application/x-www-form-urlencoded"},
            )
        return good, bad

    good, bad = asyncio.run(exercise())
    assert good.status_code == 200
    assert bad.status_code == 400


def test_pdf_and_image_benign_in_memory_roundtrips():
    from PIL import Image
    from pypdf import PdfReader, PdfWriter

    pdf = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.write(pdf)
    pdf.seek(0)
    assert len(PdfReader(pdf).pages) == 1
    png = BytesIO()
    Image.new("RGB", (2, 2), (1, 2, 3)).save(png, format="PNG")
    png.seek(0)
    with Image.open(png) as restored:
        assert restored.getpixel((0, 0)) == (1, 2, 3)


def test_synthetic_graph_and_legacy_basic_msgpack_state_remain_compatible():
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
    from langgraph.graph import END, StateGraph
    from typing_extensions import TypedDict

    class State(TypedDict):
        count: int

    graph = StateGraph(State)
    graph.add_node("increment", lambda state: {"count": state["count"] + 1})
    graph.set_entry_point("increment")
    graph.add_edge("increment", END)
    assert graph.compile().invoke({"count": 1}) == {"count": 2}
    # Basic MessagePack map emitted by the previous serializer: {"count": 1}.
    serializer = JsonPlusSerializer()
    assert serializer.loads_typed(("msgpack", b"\x81\xa5count\x01")) == {"count": 1}
    assert serializer.loads_typed(serializer.dumps_typed({"count": 2})) == {"count": 2}
