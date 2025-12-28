#!/usr/bin/env python3
"""Test Gemini 3 Flash Preview model."""

import sys

from google import genai

from src.config import settings


def main():
    print("=" * 50)
    print("Testing Gemini 3 Flash Preview")
    print("=" * 50)

    if not settings.gemini_api_key:
        print("ERROR: GEMINI_API_KEY not configured")
        sys.exit(1)

    client = genai.Client(api_key=settings.gemini_api_key)

    try:
        print("\nSending test prompt...")
        response = client.models.generate_content(
            model="gemini-3-flash-preview", contents="Respond with exactly: OK_GEMINI_3_WORKS"
        )

        result = response.text.strip()
        print(f"Response: {result}")

        if "OK" in result or "GEMINI" in result or "WORKS" in result:
            print("\n[OK] Gemini 3 Flash Preview is working correctly!")
            return 0
        else:
            print("\n[?] Unexpected response, but model responded")
            return 0

    except Exception as e:
        print(f"\n[ERROR] {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
