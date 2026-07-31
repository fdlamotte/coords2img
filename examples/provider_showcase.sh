#!/bin/sh
# Render the same location with several tile providers side by side,
# output as sixels in the terminal
# you can give a providers list on the commandline
set -eu

LAT=48.8566
LON=2.3522
ZOOM=13

PROVIDER_NAMES="${@:-opentopo carto carto_dark osm esri_satellite ign_plan}"

for provider in $PROVIDER_NAMES; do
    echo "Rendering with provider: $provider"
    coords2img -y "$LAT" -x "$LON" -z "$ZOOM" -p "$provider" -m -s
done

echo "Done."
