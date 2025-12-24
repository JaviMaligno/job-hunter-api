#!/usr/bin/env python3
"""
Test the CAPTCHA solver integration.

This script tests:
1. CAPTCHA type detection from HTML
2. Sitekey extraction
3. Token injection script generation
4. (Optional) Real CAPTCHA solving if API key is configured

Usage:
    poetry run python scripts/test_captcha_solver.py
"""

import asyncio
import sys

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
load_dotenv()

from src.integrations.captcha.solver import (
    CaptchaSolver,
    CaptchaType,
    solve_captcha,
)


# Sample HTML snippets for testing detection
SAMPLE_TURNSTILE_HTML = """
<html>
<head><title>Test Page</title></head>
<body>
    <form action="/submit" method="post">
        <input type="text" name="email" />
        <div class="cf-turnstile" data-sitekey="0x4AAAAAAAAAAAbcdefghij"></div>
        <button type="submit">Submit</button>
    </form>
</body>
</html>
"""

SAMPLE_HCAPTCHA_HTML = """
<html>
<head><title>Test Page</title></head>
<body>
    <form action="/submit" method="post">
        <input type="text" name="email" />
        <div class="h-captcha" data-sitekey="10000000-ffff-ffff-ffff-000000000001"></div>
        <button type="submit">Submit</button>
    </form>
</body>
</html>
"""

SAMPLE_RECAPTCHA_HTML = """
<html>
<head><title>Test Page</title></head>
<body>
    <form action="/submit" method="post">
        <input type="text" name="email" />
        <div class="g-recaptcha" data-sitekey="6LcR_0cUAAAAAAZzz_123abcdefg"></div>
        <button type="submit">Submit</button>
    </form>
</body>
</html>
"""

SAMPLE_NO_CAPTCHA_HTML = """
<html>
<head><title>Test Page</title></head>
<body>
    <form action="/submit" method="post">
        <input type="text" name="email" />
        <button type="submit">Submit</button>
    </form>
</body>
</html>
"""


def test_detection():
    """Test CAPTCHA type detection."""
    print("\n=== Test 1: CAPTCHA Type Detection ===")

    solver = CaptchaSolver()

    tests = [
        (SAMPLE_TURNSTILE_HTML, CaptchaType.TURNSTILE, "Turnstile"),
        (SAMPLE_HCAPTCHA_HTML, CaptchaType.HCAPTCHA, "hCaptcha"),
        (SAMPLE_RECAPTCHA_HTML, CaptchaType.RECAPTCHA_V2, "reCAPTCHA"),
        (SAMPLE_NO_CAPTCHA_HTML, None, "No CAPTCHA"),
    ]

    for html, expected_type, name in tests:
        detected = solver.detect_captcha_type(html)
        status = "[OK]" if detected == expected_type else "[FAIL]"
        print(f"  {status} {name}: detected={detected}, expected={expected_type}")


def test_sitekey_extraction():
    """Test sitekey extraction from HTML."""
    print("\n=== Test 2: Sitekey Extraction ===")

    solver = CaptchaSolver()

    tests = [
        (SAMPLE_TURNSTILE_HTML, CaptchaType.TURNSTILE, "0x4AAAAAAAAAAAbcdefghij"),
        (SAMPLE_HCAPTCHA_HTML, CaptchaType.HCAPTCHA, "10000000-ffff-ffff-ffff-000000000001"),
        (SAMPLE_RECAPTCHA_HTML, CaptchaType.RECAPTCHA_V2, "6LcR_0cUAAAAAAZzz_123abcdefg"),
    ]

    for html, captcha_type, expected_key in tests:
        extracted = solver.extract_sitekey(html, captcha_type)
        status = "[OK]" if extracted == expected_key else "[FAIL]"
        print(f"  {status} {captcha_type.value}: extracted={extracted}")


def test_injection_script():
    """Test token injection script generation."""
    print("\n=== Test 3: Injection Script Generation ===")

    solver = CaptchaSolver()
    test_token = "test_token_abc123"

    for captcha_type in [CaptchaType.TURNSTILE, CaptchaType.HCAPTCHA, CaptchaType.RECAPTCHA_V2]:
        script = solver.get_injection_script(captcha_type, test_token)
        has_token = test_token in script
        has_field = solver.get_response_field_name(captcha_type) in script
        status = "[OK]" if has_token and has_field else "[FAIL]"
        print(f"  {status} {captcha_type.value}: script length={len(script)}")


def test_solver_configuration():
    """Test solver configuration."""
    print("\n=== Test 4: Solver Configuration ===")

    solver = CaptchaSolver()

    print(f"  Solver configured: {solver.is_configured}")
    if solver.is_configured:
        print(f"  [OK] 2captcha API key is set")
    else:
        print(f"  [WARN] No 2captcha API key - real solving disabled")
        print(f"         Set TWOCAPTCHA_API_KEY in .env to enable")


async def test_balance():
    """Test balance check (only if configured)."""
    print("\n=== Test 5: Account Balance ===")

    solver = CaptchaSolver()

    if not solver.is_configured:
        print("  [SKIP] Solver not configured")
        return

    balance = await solver.get_balance()
    if balance is not None:
        print(f"  [OK] Balance: ${balance:.2f}")
    else:
        print(f"  [FAIL] Could not get balance")


async def test_real_solve():
    """Test real CAPTCHA solving (only if configured)."""
    print("\n=== Test 6: Real CAPTCHA Solving ===")
    print("  [INFO] This test requires a real CAPTCHA page")
    print("  [SKIP] Use test_orchestrator.py with a CAPTCHA-protected page")


async def main():
    print("=" * 60)
    print("CAPTCHA Solver Integration Tests")
    print("=" * 60)

    # Synchronous tests
    test_detection()
    test_sitekey_extraction()
    test_injection_script()
    test_solver_configuration()

    # Async tests
    await test_balance()
    await test_real_solve()

    print("\n" + "=" * 60)
    print("Tests complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
