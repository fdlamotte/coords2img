# Contributing

1. Fork the repo and clone your fork:
   ```
   git clone https://github.com/<you>/coords2img
   ```
2. Create a topic branch and make your change. Since everything lives in
   the single `src/coords2img/coords2img.py` file, most patches will just
   touch that.
3. Push your branch and open a pull request against `main`. Run the
   smoke test below before submitting.

Bugs and feature requests: use the
[issue tracker](https://github.com/yourname/coords2img/issues).

## Development setup

```
git clone https://github.com/yourname/coords2img
cd coords2img
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
```

Quick smoke test (no network needed):

```
coords2img --help-json
python -m coords2img --help
```

Or just run the file directly without installing the package:

```
pip install Pillow requests
python3 src/coords2img/coords2img.py
```

Please keep new marker/line/shape fields documented in `JSON_HELP_TEXT`
(inside `src/coords2img/coords2img.py`) and in the README.
