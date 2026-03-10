#!/usr/bin/env python3
"""
Wrapper script for prediction market arbitrage scanner
Handles module imports correctly
"""
import sys
import os

# Add project to path
sys.path.insert(0, '/home/ryan/openclaw-orchestration-stack')
sys.path.insert(0, '/home/ryan/openclaw-orchestration-stack/devclaw-runner/src')

# Import and run
from prediction_markets.arb_scanner import main
import asyncio

if __name__ == "__main__":
    result = asyncio.run(main())
    print(f"Scan complete. Found {result} opportunities.")
