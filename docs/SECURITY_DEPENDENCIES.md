# Security dependency update (22 October 2026)

The application lock is regenerated with Poetry 2.3.2. Explicit minimums constrain
the corrected CA, TLS, HTTP parsing, JWT dependency, PDF/image and serialization
cohorts. No application authentication, token format, database model, provider
workflow or stored checkpoint is transformed by this patch.

## Compatibility decisions

- FastAPI 0.136.3 / Starlette 1.3.1 restore form limits. The browser service keeps
  the same constrained framework cohort in its independent requirements file.
- Cryptography 50.0.2 is compatible with the existing python-jose API. Bcrypt is
  constrained to 4.3.0 because passlib 1.7.4 cannot initialize the bcrypt 5 backend
  to verify existing hashes. This preserves the bcrypt password scheme.
- LangGraph 1.2.16 requires checkpoint >=4.3 and SDK >=0.4.6; LangChain Core 1.7
  requires LangSmith's newer WebSocket dependency, so the old ^14 bound becomes
  >=15,<16. No `src` module imports LangGraph, LangChain or the websockets package
  directly. Synthetic tests cover a small StateGraph and basic legacy MessagePack
  state. This is not evidence that arbitrary historical Python object checkpoints
  can be loaded; no persisted checkpoint or business data is read or changed.
- Langfuse remains on its existing 2.x API, including decorators. Its packaging<25
  constraint conflicts with patched virtualenv's packaging>=26.3. Therefore Git
  hook tooling is isolated in `requirements-dev-tools.txt`; it is no longer
  installed into the application Poetry environment. Install it in a separate
  environment using the corrected pip/CA bootstrap, or an isolated uv tool run.
- pytest-playwright moves from 0.6 to 0.10 because the old plugin requires
  pytest<9 and excludes pytest's fixed release. No browser is downloaded or
  launched by the offline security contracts.

## Runtime and verification

Docker and CI bootstrap the SHA256-verified pip 26.2.2 wheel before resolving
packages, install certifi 2026.10.19 and Poetry 2.3.2, and use Python 3.11.17.
Docker installs the committed production lock with `--only main --no-root` before
copying the application. Poetry and virtualenv stay in the global tooling
environment; application packages install into `/app/.venv`, which supplies the
runtime PATH. This preserves Langfuse2's packaging<25 requirement without
downgrading the tooling environment's packaging>=26.3. Ready PRs build the image
once when container inputs change and run `pip check` in both environments with
network disabled and no application startup. No such image check was run locally.
Updated base images still need a separately authorized
fresh pull and uncached rebuild; these source changes do not establish a live
deployment or image build.

Run only the offline contract file when verifying this patch locally:

```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest security_contracts/test_runtime_dependencies.py -q
```

It uses the actual authentication router with an async database mock, synthetic
keys/passwords, in-memory PDF/PNG data and a synthetic graph. It does not import
`src.main`, start application jobs, connect to providers or read persistent data.
The CI unit suite remains reserved for Ready PRs. `ready_for_review` is an
explicit trigger; concurrency cancels superseded PR runs and never main runs.
The scheduled Keep Alive health check is unchanged and is not a verification
step for this patch.

## Residual advisories

python-jose 3.5.0 has no released fix for DER public-key algorithm confusion
(GHSA-3qf3-8w2g-rqmx). The service retains its configured algorithm allowlist;
tests cover legitimate HS256/RS256 PEM keys and mismatched HMAC rejection. They
do not prove arbitrary custom algorithm/key configurations safe. ECDSA 0.19.2
also retains the unfixed Minerva timing advisory (GHSA-wj6h-64fc-37mp). Any
algorithm removal or key migration needs an explicit compatibility decision.

Sources: [Python CA incident](https://discuss.python.org/t/information-for-python-users-regarding-emudhra-emsign-ca-certificate-security-incident/109576),
[virtualenv fixes and bundled pip](https://virtualenv.pypa.io/en/latest/changelog.html),
[Starlette form limits](https://github.com/Kludex/starlette/security/advisories/GHSA-82w8-qh3p-5jfq).

The Docker build context excludes host virtualenvs, Git metadata, credentials,
local databases and audit caches. This keeps COPY . . from replacing the image's
application environment or copying those local files into the image. Changes to
.dockerignore also select the Ready-only container dependency check. CI explicitly
grants contents:read and pull-requests:read for its read-only PR path query.

Hosted CI's real main import exposed an existing undefined DBSession annotation
on mark_session_applied. The router now uses the existing DbDep dependency alias,
with no change to its endpoint body, authentication or data operations. The focused
security_contracts/test_application_import.py imports the real router and checks
that FastAPI registers get_db while provider constructors, HTTP transports and
database connect are blocked. It passed locally without calling endpoints or
starting lifespan. The focused environment lacks optional Gemini SDKs; full
latest-head hosted main import remains required evidence for that broader graph.

## Draft CI lint follow-up (23 October 2026)

The follow-up begins at `557dace9f0d0438f3299e82386c26b6b17e51cc3`.
Ruff 0.8.6 reproduced the 24 remaining diagnostics and 18 files requiring
formatting. The patch removes unused imports/locals, redundant f-string prefixes
and the redundant inner settings import; uses Python 3.11's identical built-in
TimeoutError alias; and sorts imports. It does not add suppressions or change
lint/type configuration. Provider prompts, authentication, route bodies, document
output and stored data contracts remain unchanged.

The undefined BrowserServiceClient name was a stale local attribute annotation,
not a NameError observed while running a business job. The agent already creates
BrowserlessClient inside its existing async context. Its annotation now names
that real CDP client, without adding the retired HTTP client or changing the
factory/transport. The new resource contract first reproduced the unresolved
annotation; the real page-info mapping contract already passed before the fix.

Focused verification passes:

- Ruff check and format-check across all 131 tracked Python files plus the new
  contract file: zero diagnostics and 132 files formatted. The formatter changed
  18 existing files and the new fixture; ASTs before/after formatting are identical.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest security_contracts/test_browser_resource.py -q --tb=short -p no:cacheprovider`:
  two contracts pass. The constructor and page-info method use the real
  Browserless DOM/content/URL methods over synthetic Page/Element objects.
  Gemini and Playwright SDK boundaries are stand-ins; HTTP transports, provider
  constructors, database connect, browser startup and dotenv-file loading are
  blocked. The orchestration job and browser context are never entered.
  Disabling optional pytest plugins leaves an asyncio_mode configuration warning;
  these synchronous tests manage their own in-memory event loop.
- Mypy 1.19.0 from the unchanged lock passes the seven affected agent, route,
  CLI and service files using the existing configuration and
  `--ignore-missing-imports`. Its four tool wheels were added to the isolated
  environment, without a full dependency sync. Optional SDK imports remain
  missing there, so this does not replace the complete hosted type/import gate.
- The isolated environment passes `pip check` after that tool installation.

Earlier successful auth/graph contracts were not repeated for mechanical lint
and AST-equivalent formatting. Full latest-head hosted CI and image dependency
checks remain required; no full suite, provider, database, browser, scheduled job,
Docker build, push, deployment or merge was executed by this local follow-up.
