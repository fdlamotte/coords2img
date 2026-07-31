"""
coords2img -- generate static map images (PNG or terminal sixel) from
coordinates, with a JSON-driven format for markers, lines/paths, arrows,
and per-item styling.

All the actual logic lives in coords2img.py (a single, standalone-runnable
file you can also just copy out and use with `python3 coords2img.py ...`).
This __init__.py only re-exports the useful bits for `import coords2img`.
"""
from .coords2img import (
    MAP_SERVERS,
    SHAPES,
    LINE_STYLES,
    CURVE_TYPES,
    ARROW_MODES,
    generate_map_by_size,
    parse_color,
    resolve_field,
    display_sixel_via_system,
    main,
)

__version__ = "0.1.0"

__all__ = [
    "MAP_SERVERS",
    "SHAPES",
    "LINE_STYLES",
    "CURVE_TYPES",
    "ARROW_MODES",
    "generate_map_by_size",
    "parse_color",
    "resolve_field",
    "display_sixel_via_system",
    "main",
    "__version__",
]
