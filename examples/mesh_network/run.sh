#!/bin/sh
# Plot meshcore-cli node positions on a map.
# Real usage: meshcore-cli export-nodes > nodes.json (or whatever your
# version's export command is called), then point this at that file.
set -eu

NODES_FILE="${1:-sample_nodes.json}"

jq -f meshcore2markers.jq "$NODES_FILE" | coords2img -s
