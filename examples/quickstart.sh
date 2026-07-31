#!/bin/sh
# The absolute minimum: display Paris in the terminal via sixel.
# Requires img2sixel (from libsixel) and a sixel-capable terminal.
exec coords2img -y 48.8566 -x 2.3522 -z 12 -m -s
