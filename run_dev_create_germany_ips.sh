#!/usr/bin/env bash
set -euo pipefail

# Always run from the directory where the script lives (repo root)
cd "$(dirname "$0")"

# Run the generator
python3 ./create_germany_ips.py
