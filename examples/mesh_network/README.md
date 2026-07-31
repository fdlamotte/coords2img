# mesh_network example

Converts a [meshcore-cli](https://github.com/meshcore-dev/meshcore-cli)
node export (a dict keyed by public key, with `adv_lat`/`adv_lon`/`adv_name`
per node) into coords2img's marker format, using `jq`.

Nodes with no GPS fix (`adv_lat`/`adv_lon` both `0.0`, meshcore's sentinel
for "unknown") are filtered out.

```
jq -f meshcore2markers.jq sample_nodes.json
```

```json
[
  {
    "lat": 18.445885,
    "lon": -69.94508,
    "caption": "M9"
  }
]
```

Run the whole pipeline (jq -> coords2img) with:

```
./run.sh sample_nodes.json
```

or point it at a real export from your own node.
