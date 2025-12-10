#!/bin/bash
# Activate the virtual environment
# not needed
# source /home/zenogries/berlin-chat-dev-interface/venv/bin/activate

# cd to repo root
cd /home/zenogries/berlin-chat-dev-interface

# Run the Python script
python3 /home/zenogries/berlin-chat-dev-interface/create_germany_ips.py

# reloading caddy is within .py and not here so that it does not get reloaded unnecessarily
