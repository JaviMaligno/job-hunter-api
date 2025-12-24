#!/usr/bin/env python3
"""List available Gemini models."""

import os
from dotenv import load_dotenv

load_dotenv()

from google import genai

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

client = genai.Client(api_key=GEMINI_API_KEY)

print("Available Gemini Models:")
print("=" * 60)

for model in client.models.list():
    name = model.name
    # Filter to show only generative models
    if "gemini" in name.lower():
        print(f"  {name}")
        if hasattr(model, 'supported_generation_methods'):
            print(f"    Methods: {model.supported_generation_methods}")
