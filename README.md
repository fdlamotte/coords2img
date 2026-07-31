# coords2img

Generate static map images — as a PNG file or directly as [sixel](https://en.wikipedia.org/wiki/Sixel)
graphics in your terminal — from a set of coordinates. Comes with a small
JSON format for annotating the map with markers, lines and shapes.

```
$ coords2img -y 48.8566 -x 2.3522 -z 12 -s
```

## Features

- Multiple free tile providers built in: OpenTopoMap, Carto (light/dark),
  OpenStreetMap.fr, Google (satellite/hybrid/roads), Esri World
  Imagery, and IGN Géoplateforme (France) — or point it at any custom
  `{z}/{x}/{y}` tile URL template.
- On-disk tile caching (`~/.cache/coords2img`).
- Output as a PNG file, straight to the terminal via sixel (`img2sixel`
  must be installed).
- A JSON document — from a file, stdin, or `-i`/`--input` — can describe:
  - **markers**: positioned points with a caption, id, color, shape
    (square/circle/cross/diamond), stroke width, font color/size, and an
    optional `hide` flag (useful as an invisible anchor point for lines);
    a marker without coordinates falls back to the map's center.
  - **lines**: straight or Catmull-Rom-smoothed (`"curve": "bezier"`)
    paths across 2+ points (referenced by marker id, `[lat, lon]`, or
    `{"lat":..., "lon":...}`), with color, width, style
    (plain/dotted/dash), and optional arrowheads (`begin`/`end`/`both`).
  - **shapes**: 
- Run `coords2img --help-json` for the full field-by-field reference.

## Install

**Standalone**, no packaging involved:

```
curl -O https://raw.githubusercontent.com/yourname/coords2img/main/src/coords2img/coords2img.py
pip install Pillow requests
python3 coords2img.py -y 48.8566 -x 2.3522 -z 12 -s
```

**From PyPI**, gets you a `coords2img` command on your `PATH`:

```
pip install coords2img
```

**From source**, same result:

```
git clone https://github.com/yourname/coords2img
cd coords2img
pip install .
```

Sixel output additionally requires the `img2sixel` binary (from
[libsixel](https://github.com/saitoha/libsixel)) on your `PATH`, and a
terminal that understands sixel graphics (e.g. xterm, foot, wezterm,
mlterm, or a `tmux`/`screen` session configured to pass them through).

## Usage

```
coords2img -y <lat> -x <lon> -z <zoom> [-W width] [-H height] [-o file.png | -s] [options]
```

(or `python3 coords2img.py ...` if running it standalone)

Common flags:

| Flag | Meaning |
|---|---|
| `-y`, `--lat` / `-x`, `--lon` | Center coordinates (degrees) |
| `-z`, `--zoom` | Tile zoom level |
| `-W`, `--width` / `-H`, `--height` | Output size in pixels |
| `-o`, `--output` | Save to a PNG file |
| `-i`, `--input FILE` | Read JSON from a file instead of stdin |
| `-s`, `--sixel` | Display in the terminal via sixel |
| `-m`, `--marker` | Draw a marker at the center coordinates |
| `-p`, `--provider` | Tile provider (see list above) |
| `-u`, `--custom-url` | Custom `{s}/{z}/{x}/{y}` tile URL template |
| `-J`, `--markers-stdin` | Explicitly read JSON from stdin |
| `-v`, `--verbose` | Print cache/network/drawing details to stderr |
| `--help-json` | Print the full JSON format reference |

Run `coords2img --help` for the complete list.

### JSON input

The JSON document can be a plain array of markers, or an object whose
`markers` / `lines` / `shapes` keys hold those arrays, alongside app 
parameters (overridden by cli arguments):

```
echo '{
  "zoom": 13,
  "marker_defaults": {"shape": "circle", "color": "green"},
  "line_defaults": {"type": "dash", "width": 2},
  "markers": [
    {"id": "start", "lat": 47.752, "lon": -3.402, "caption": "Start"},
    {"id": "end", "lat": 47.746, "lon": -3.394, "caption": "End", "shape": "diamond"}
  ],
  "lines": [
    {"points": ["start", "end"], "color": "blue", "curve": "bezier", "arrow": "end"}
  ],
  "shapes": [
    { "type": "circle", "center": "end", "color": "blue", "radius_km": 1.5 }
  ]
}' | coords2img -y 47.749 -x -3.398 -p carto -o trip.png
```

See [`examples/`](examples/) for more, and `coords2img --help-json` for
the complete field reference.

## License

MIT — see [LICENSE](LICENSE).
