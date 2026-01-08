#!/bin/sh
set -e

# Install Python dependencies
pip install fastapi uvicorn playwright python-multipart

# Install Playwright with Chromium browser and dependencies
playwright install --with-deps chromium

echo "Playwright environment ready!"
