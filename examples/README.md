# Examples

A few ready-to-run demonstrations. All commands assume `coords2img` is
installed and you're in this `examples/` directory. (If running the
script standalone instead, swap `coords2img` for
`python3 ../coords2img.py`.)

| File | Shows off |
|---|---|
| `quickstart.sh` | The absolute minimum: one coordinate, one sixel |
| `treasure_map.json` | Fun themed styling: custom shapes, colors, dotted trail, "X marks the spot" |
| `zones.json` | The `shapes` array: circle/rect/poly with solid/hatch/cross fills, opacity, rotation |
| `tour.json` | Emoji as marker icons (`shape: "🏠"`) and in line labels (`"🚶 10 min"`) |
| `provider_showcase.sh` | Rendering the same spot across several tile providers |
| `mesh_network/` | JQ integration: converting a `meshcore-cli` node export to markers |

Run any `.json` example like this:

```
coords2img -i tour.json -s
```

or save it to a file instead of the terminal:

```
coords2img -i treasure_map.json -o treasure_map.png
```
