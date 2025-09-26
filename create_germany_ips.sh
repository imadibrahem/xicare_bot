#!/bin/bash
# Create germany_ips.caddy with all German IPv4 + IPv6 ranges

OUTPUT_FILE="germany_ips.caddy"

# Ensure the file exists and is empty
> "$OUTPUT_FILE"

# Add IPv4 ranges (de.zone)
if [ -f "de.zone" ]; then
  while read -r line; do
    echo -n "$line " >> "$OUTPUT_FILE"
  done < de.zone
fi

# Add IPv6 ranges (de6.zone)
if [ -f "de6.zone" ]; then
  while read -r line; do
    echo -n "$line " >> "$OUTPUT_FILE"
  done < de6.zone
fi

# Prepend the directive name `remote_ip` at the very start
sed -i '1s/^/remote_ip /' "$OUTPUT_FILE"

echo "Generated $OUTPUT_FILE"

