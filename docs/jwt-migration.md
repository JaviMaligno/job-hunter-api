# JWT dependency migration (23 October 2026)

This change follows reviewed source head `adb62ddf0eb3bb4c4cd57d40a8dd091ef4ad6703`. The application now uses
`PyJWT[crypto]>=2.15.1,<3`, with the existing corrected cryptography cohort. Both
python-jose and ECDSA are absent from the regenerated production lock/export.
Their upstream advisories remain unfixed: [DER/HMAC confusion in python-jose](https://github.com/advisories/GHSA-3qf3-8w2g-rqmx)
and [Minerva in python-ecdsa](https://github.com/tlsfuzzer/python-ecdsa/security/advisories/GHSA-wj6h-64fc-37mp).
This removes those application dependencies; it does not invent an upstream fix
or establish that every other package, deployment key or image layer is safe.

## Compatibility and validation

Signing algorithms come from the same trusted configuration, never the token
header. Job keeps configurable HS/RS/ES algorithms, its `type` access/refresh claim, `TokenError`, and HTTP 401/Bearer error family. Claim names, token strings, key selection, account permissions
and the existing token-error result remain compatible. No signing-key rotation,
refresh-token storage transformation, schema migration or provider call occurs.

Signature, expiration, not-before, subject, JWT-ID and audience validation remain
enabled. Since these callers provide no audience or OIDC access-token context,
any present `aud` or `at_hash` is rejected after signature verification, including
empty values that a simple import replacement would otherwise accept. Optional
claims keep their existing presence policy; application token-type/subject checks
stay at their original callers. Malformed numeric claims use the token failure
API rather than escaping as decoder type errors.

Two documented security tightenings use the new library defaults: future `iat`
values are rejected, and `exp == now` is expired. No leeway or verification bypass
is added. Legacy tokens retain their signed timestamps and are accepted while
valid under that policy. [PyJWT's API](https://pyjwt.readthedocs.io/en/stable/api.html)
and [2.15.1 source](https://github.com/jpadilla/pyjwt/tree/2.15.1) document the
signature/claim options and DER-key rejection with the crypto extra.

RSA verification extracts the public key from a configured RSA private PEM or
PEM certificate, preserving the previous shared-config format support. This
adapter applies only to configured RS256/384/512; HS key rejection and ES behavior
remain with PyJWT. Certificates remain configured public-key containers. The
refresh token's original string, SHA256 storage hash and aware expiry remain
unchanged. The old package's RSA/ASN.1 dependencies remain where Google Auth still
requires them; only jose and ECDSA are pruned (143 to 141 lock records, with no
unrelated version changes).

## Focused evidence

The three original implementations all accepted the synthetic DER-as-HMAC,
future-iat and exact-expiry cases: nine expected RED failures. The configurable
RSA implementations additionally exposed four migration RED failures for a
private PEM used by both issuance/verification and for a PEM certificate. Those
contracts pass with the explicit RSA verification-key adaptation.

Five HS256/384/512, RS256 and ES256 legacy tokens were generated using python-jose 3.5.0 with invented
identities and keys. Across all three repositories, eleven algorithm/repository
pairs verify in both directions with PyJWT 2.15.1. Committed fixtures contain
synthetic tokens and public keys only, plus an explicitly invented shared test
secret; RSA/EC private keys exist only in memory. Future tests load these fixtures
without adding jose back as a development dependency.

The final focused selection passes 38 cases. It covers old/new tokens, refresh
semantics where present, malformed claims, algorithm/key mismatch, unsigned
input, approved date tightenings, and actual authentication dependencies. Real
HTTP/DNS, subprocess startup, provider constructors, database connections and
dotenv-file loading are denied; application imports receive only synthetic
settings. A signed role claim cannot replace the database principal returned by
the dependency mock. No application lifespan, business job or persistent data is
used.

```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest security_contracts/test_jwt_migration.py security_contracts/test_runtime_dependencies.py::test_existing_hs256_access_refresh_and_hash_contract security_contracts/test_runtime_dependencies.py::test_hmac_algorithm_and_signature_mismatch_remain_rejected security_contracts/test_runtime_dependencies.py::test_configured_rsa_pem_and_der_hmac_confusion security_contracts/test_runtime_dependencies.py::test_real_auth_router_login_preserves_response_and_token_contract -q --tb=short -p no:cacheprovider
```

Scoped Ruff check/format and mypy for `src/auth/jwt.py` pass, as does the focus environment pip check. Full SDK/source type validation remains a hosted-CI gate. The formatter preserves the compared ASTs. Some deliberately short
negative-test keys produce PyJWT key-length warnings; no warning filter or
production key-policy change is introduced. Local verification reused isolated
focus environments, which may still contain the former packages for legacy
proof; complete fresh installs use the committed lock. Final-head hosted CI,
independent review and image checks remain separate gates. No full local suite,
server, browser, Docker build, push, deployment or merge is part of this patch.
