#!/bin/bash
# Activate the virtual environment
# not needed
# source /home/zenogries/berlin-chat-dev-interface/venv/bin/activate

# Run the Python script
python /home/zenogries/berlin-chat-dev-interface/create_germany_ips.py

# reloading caddy is within .py and not here so that it does not get reloaded unnecessarily