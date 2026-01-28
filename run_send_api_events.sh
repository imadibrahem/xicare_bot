#!/usr/bin/env bash
set -e

# Load conda into this shell
source /home/sqlxpert851/miniconda3/etc/profile.d/conda.sh

# cd to repo root
cd /home/zenogries/berlin-chat-dev-interface

# conda environment
conda activate berlin-chatbot

# Run the Python script
python3 /home/zenogries/berlin-chat-dev-interface/send_api_events.py
