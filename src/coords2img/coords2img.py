#!/usr/bin/env python3
import argparse
import json
import math
import sys
import subprocess
import os
import tempfile
from io import BytesIO
import requests
from PIL import Image, ImageDraw, ImageFont, ImageColor, ImageChops

MAP_SERVERS = {
    "opentopo": "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
    "carto": "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
    "carto_dark": "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
    "osm" : "https://{s}.tile.openstreetmap.fr/osmfr/{z}/{x}/{y}.png",
    "google_sat": "https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
    "google_hybrid": "https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
    "google_roads": "https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}",
    "esri_satellite": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    "ign_plan": "https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2&STYLE=normal&FORMAT=image/png&TILEMATRIXSET=PM&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}",
    "ign_ortho": "https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=HR.ORTHOIMAGERY.ORTHOPHOTOS&STYLE=normal&FORMAT=image/jpeg&TILEMATRIXSET=PM&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}",
}

SUBDOMAINS=['a', 'b', 'c']
SDNB = len(SUBDOMAINS)

CACHE_DIR = os.path.expanduser("~/.cache/coords2img")

def lat_lon_to_tile_fractional(lat, lon, zoom):
    lat_rad = math.radians(lat)
    n = 2.0 ** zoom
    x = (lon + 180.0) / 360.0 * n
    y = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n
    return x, y

def get_tile_image(provider_name, s, z, x, y, server_url, write_cache=False, verbose=False):
    tile_filename = f"{provider_name}_{z}_{x}_{y}.png"
    cache_path = os.path.join(CACHE_DIR, tile_filename)

    if os.path.exists(cache_path):
        try:
            if os.path.getsize(cache_path) > 0:
                if verbose:
                    print(f"[Cache] Reading tile {z}/{x}/{y}", file=sys.stderr)
                return Image.open(cache_path)
            else:
                os.remove(cache_path)
        except Exception as e:
            if verbose:
                print(f"[Cache] Deleted corrupted tile: {e}", file=sys.stderr)
            pass

    url = server_url.format(s=s, z=z, x=x, y=y)

    if verbose:
        print(f"[Network] Request: {url}", file=sys.stderr)

    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            tile_data = response.content

            if write_cache:
                if verbose:
                    print(f"[Cache] Tile {tile_filename} written", file=sys.stderr)
                with open(cache_path, "wb") as f:
                    f.write(tile_data)

            return Image.open(BytesIO(tile_data))
        else:
            if verbose:
                print(f"[Network] HTTP error {response.status_code} on tile {z}/{x}/{y}", file=sys.stderr)
    except Exception as e:
        if verbose:
            print(f"[Network] Network connection failure: {e}", file=sys.stderr)
        pass

    return None

def load_caption_font(size=12, verbose=False):
    for font_name in ("DejaVuSans.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(font_name, size)
        except Exception as e:
            if verbose:
                print(f"[Font] Could not load '{font_name}' at size {size}: {e}", file=sys.stderr)
            continue
    if verbose:
        print("[Font] No TrueType caption font found (tried DejaVuSans.ttf, Arial.ttf) -- "
              "falling back to PIL's built-in bitmap font. Install DejaVu Sans for normal-looking "
              "captions (e.g. 'apt install fonts-dejavu-core' or 'apk add ttf-dejavu').",
              file=sys.stderr)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        # Older Pillow versions don't support the size kwarg
        return ImageFont.load_default()

_UNSET = object()


def resolve_field(node, defaults, field, hardcoded):
    v = node.get(field, _UNSET)
    if v is not _UNSET and v is not None:
        return v
    v = defaults.get(field, _UNSET)
    if v is not _UNSET and v is not None:
        return v
    return hardcoded

def parse_color(value, fallback):
    if value is None:
        return fallback
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        try:
            return tuple(int(c) for c in value[:3])
        except (TypeError, ValueError):
            return fallback
    if isinstance(value, str):
        try:
            return ImageColor.getrgb(value)
        except ValueError:
            return fallback
    return fallback

SHAPES = ("square", "circle", "cross", "diamond")
LINE_STYLES = ("plain", "dotted", "dash")
CURVE_TYPES = ("straight", "bezier")

def draw_marker_shape(draw, x, y, shape="square", color=(255, 0, 0), radius=4, width=2):
    shape = (shape or "square").lower()
    if shape == "circle":
        draw.ellipse([x - radius, y - radius, x + radius, y + radius], outline=color, width=width)
    elif shape == "cross":
        draw.line([(x - radius, y), (x + radius, y)], fill=color, width=width)
        draw.line([(x, y - radius), (x, y + radius)], fill=color, width=width)
    elif shape == "diamond":
        pts = [(x, y - radius), (x + radius, y), (x, y + radius), (x - radius, y)]
        for i in range(4):
            draw.line([pts[i], pts[(i + 1) % 4]], fill=color, width=width)
    else:  # "square" and unknown fallbacks
        draw.rectangle([x - radius, y - radius, x + radius, y + radius], outline=color, width=width)

def smooth_path(points, samples_per_segment=16):
    if len(points) < 3:
        return list(points)

    padded = [points[0]] + list(points) + [points[-1]]
    curve = []
    for i in range(1, len(padded) - 2):
        p0, p1, p2, p3 = padded[i - 1], padded[i], padded[i + 1], padded[i + 2]
        for s in range(samples_per_segment):
            t = s / samples_per_segment
            t2 = t * t
            t3 = t2 * t
            x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t
                       + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                       + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
            y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t
                       + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                       + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            curve.append((x, y))
    curve.append(points[-1])
    return curve

def draw_styled_line(draw, points, color=(0, 0, 0), width=2, style="plain"):
    style = (style or "plain").lower()

    if style == "plain":
        draw.line(points, fill=color, width=width, joint="curve")
        return

    dash_len, gap_len = (2, 6) if style == "dotted" else (10, 6)  # dash / fallback

    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        seg_len = math.hypot(x2 - x1, y2 - y1)
        if seg_len == 0:
            continue
        dx, dy = (x2 - x1) / seg_len, (y2 - y1) / seg_len
        dist = 0.0
        draw_on = True
        while dist < seg_len:
            step = dash_len if draw_on else gap_len
            next_dist = min(dist + step, seg_len)
            if draw_on:
                sx, sy = x1 + dx * dist, y1 + dy * dist
                if style == "dotted":
                    r = max(width / 2, 1)
                    draw.ellipse([sx - r, sy - r, sx + r, sy + r], fill=color)
                else:
                    ex, ey = x1 + dx * next_dist, y1 + dy * next_dist
                    draw.line([(sx, sy), (ex, ey)], fill=color, width=width)
            dist = next_dist
            draw_on = not draw_on

ARROW_MODES = ("begin", "end", "both")

def draw_arrowhead(draw, tip, direction, color, size=10):
    dx, dy = direction
    if dx == 0 and dy == 0:
        return
    angle = math.atan2(dy, dx)
    spread = math.radians(25)
    left = (tip[0] - size * math.cos(angle - spread), tip[1] - size * math.sin(angle - spread))
    right = (tip[0] - size * math.cos(angle + spread), tip[1] - size * math.sin(angle + spread))
    draw.polygon([tip, left, right], fill=color)

def normalize(dx, dy):
    length = math.hypot(dx, dy)
    if length == 0:
        return (1.0, 0.0)
    return dx / length, dy / length

def point_and_tangent_at(points, fraction):
    if len(points) == 1:
        return points[0], (1.0, 0.0)

    seg_lengths = [math.hypot(points[i + 1][0] - points[i][0], points[i + 1][1] - points[i][1])
                   for i in range(len(points) - 1)]
    total = sum(seg_lengths)
    if total == 0:
        return points[0], (1.0, 0.0)

    target = max(0.0, min(1.0, fraction)) * total
    acc = 0.0
    for i, seg_len in enumerate(seg_lengths):
        if target <= acc + seg_len or i == len(seg_lengths) - 1:
            local_t = (target - acc) / seg_len if seg_len > 0 else 0.0
            local_t = max(0.0, min(1.0, local_t))
            x = points[i][0] + (points[i + 1][0] - points[i][0]) * local_t
            y = points[i][1] + (points[i + 1][1] - points[i][1]) * local_t
            return (x, y), (points[i + 1][0] - points[i][0], points[i + 1][1] - points[i][1])
        acc += seg_len
    return points[-1], (points[-1][0] - points[-2][0], points[-1][1] - points[-2][1])

EMOJI_RANGES = (
    (0x1F1E6, 0x1F1FF),  # regional indicators (flags)
    (0x1F300, 0x1FAFF),  # misc symbols & pictographs, emoticons, transport, supplemental
    (0x2600, 0x27BF),    # misc symbols, dingbats
    (0x2300, 0x23FF),    # misc technical (hourglass, watch, ...)
    (0x2B00, 0x2BFF),    # misc symbols and arrows
    (0x1F000, 0x1F0FF),  # mahjong / dominoes / playing cards
    (0xFE0F, 0xFE0F),    # variation selector-16 (forces emoji presentation)
    (0x200D, 0x200D),    # zero-width joiner (compound emoji like family/flags)
)

EMOJI_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",             # Debian/Ubuntu
    "/usr/share/fonts/noto/NotoColorEmoji.ttf",                      # Alpine/postmarketOS
    "/usr/share/fonts/google-noto-emoji/NotoColorEmoji.ttf",         # Fedora
    "/usr/share/fonts/google-noto-color-emoji-fonts/NotoColorEmoji.ttf",
    "/usr/local/share/fonts/NotoColorEmoji.ttf",
    "~/.local/share/fonts/NotoColorEmoji.ttf",
    "NotoColorEmoji.ttf",
    "seguiemj.ttf",                                                  # Windows
    "/System/Library/Fonts/Apple Color Emoji.ttc",                   # macOS
    # Monochrome fallback: a regular scalable outline font
    "/usr/share/fonts/truetype/noto/NotoEmoji-Regular.ttf",
    "/usr/share/fonts/noto/NotoEmoji-Regular.ttf",
    "NotoEmoji-Regular.ttf",
)

_emoji_font_cache = {"font": "unset"}
_emoji_glyph_cache = {}

def is_emoji_char(ch):
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in EMOJI_RANGES)

def split_text_runs(text):
    """Split `text` into (substring, is_emoji) runs of consecutive
    emoji/non-emoji characters."""
    runs = []
    if not text:
        return runs
    cur = text[0]
    cur_emoji = is_emoji_char(text[0])
    for ch in text[1:]:
        e = is_emoji_char(ch)
        if e == cur_emoji:
            cur += ch
        else:
            runs.append((cur, cur_emoji))
            cur = ch
            cur_emoji = e
    runs.append((cur, cur_emoji))
    return runs

def get_emoji_font(verbose=False):
    if _emoji_font_cache["font"] != "unset":
        return _emoji_font_cache["font"]

    found, found_path = None, None
    tried_paths = []
    for raw_path in EMOJI_FONT_CANDIDATES:
        path = os.path.expanduser(raw_path)
        tried_paths.append(path)
        for size in (109, 128, 96, 160, 64, 32):
            try:
                found = ImageFont.truetype(path, size)
                found_path = path
                break
            except Exception:
                continue
        if found:
            break

    if verbose:
        if found is not None:
            print(f"[Font] Using emoji font: {found_path}", file=sys.stderr)
        else:
            print("[Font] No emoji font found -- emoji in captions/labels will be drawn with the "
                  "regular caption font (likely as blank/placeholder glyphs). Tried: "
                  + ", ".join(dict.fromkeys(tried_paths)), file=sys.stderr)
            print("[Font] Install a color emoji font to fix this, e.g.:", file=sys.stderr)
            print("[Font]   Debian/Ubuntu     : apt install fonts-noto-color-emoji", file=sys.stderr)
            print("[Font]   Alpine/postmarketOS: apk add font-noto-emoji", file=sys.stderr)
            print("[Font]   Fedora             : dnf install google-noto-emoji-color-fonts", file=sys.stderr)
            print("[Font] Or pass --no-emoji to silence this and draw emoji as plain text.", file=sys.stderr)

    _emoji_font_cache["font"] = found
    return found

def render_emoji_run(run_text, target_size, verbose=False):
    cache_key = (run_text, target_size)
    if cache_key in _emoji_glyph_cache:
        return _emoji_glyph_cache[cache_key]

    result = None
    font = get_emoji_font(verbose=verbose)
    if font is not None:
        try:
            probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
            bbox = probe.textbbox((0, 0), run_text, font=font, embedded_color=True)
            w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            if w > 0 and h > 0:
                glyph = Image.new("RGBA", (w, h), (0, 0, 0, 0))
                ImageDraw.Draw(glyph).text((-bbox[0], -bbox[1]), run_text, font=font, embedded_color=True)
                scale = target_size / h
                new_size = (max(1, round(w * scale)), max(1, round(h * scale)))
                result = glyph.resize(new_size, Image.Resampling.LANCZOS)
        except Exception:
            result = None

    _emoji_glyph_cache[cache_key] = result
    return result

def draw_mixed_text(image, x, y, text, font, fill, halo=True, emoji=True, verbose=False):
    draw = ImageDraw.Draw(image)
    runs = split_text_runs(text)

    if not emoji or not get_emoji_font(verbose=verbose) or not any(is_emj for _, is_emj in runs):
        if halo:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if dx or dy:
                        draw.text((x + dx, y + dy), text, font=font, fill=(255, 255, 255))
        draw.text((x, y), text, font=font, fill=fill)
        return draw.textlength(text, font=font)

    ascent, descent = font.getmetrics()
    target_size = ascent + descent
    cur_x = x
    for run_text, is_emj in runs:
        if is_emj:
            glyph = render_emoji_run(run_text, target_size, verbose=verbose)
            if glyph is not None:
                image.paste(glyph, (round(cur_x), round(y)), glyph)
                cur_x += glyph.width
                continue
            # no usable glyph -- fall through and draw the raw codepoints
            # with the regular font instead of silently dropping them
        if halo:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if dx or dy:
                        draw.text((cur_x + dx, y + dy), run_text, font=font, fill=(255, 255, 255))
        draw.text((cur_x, y), run_text, font=font, fill=fill)
        cur_x += draw.textlength(run_text, font=font)
    return cur_x - x

def measure_mixed_text(image, text, font, emoji=True, verbose=False):
    draw = ImageDraw.Draw(image)
    runs = split_text_runs(text)

    if not emoji or not get_emoji_font(verbose=verbose) or not any(is_emj for _, is_emj in runs):
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]

    ascent, descent = font.getmetrics()
    target_size = ascent + descent
    total_w = 0.0
    max_h = target_size
    for run_text, is_emj in runs:
        if is_emj:
            glyph = render_emoji_run(run_text, target_size, verbose=verbose)
            if glyph is not None:
                total_w += glyph.width
                max_h = max(max_h, glyph.height)
                continue
        bbox = draw.textbbox((0, 0), run_text, font=font)
        total_w += draw.textlength(run_text, font=font)
        max_h = max(max_h, bbox[3] - bbox[1])
    return total_w, max_h

def draw_line_label(image, anchor, font, text, color, emoji=True, verbose=False):
    w, h = measure_mixed_text(image, text, font, emoji=emoji, verbose=verbose)
    tx = anchor[0] - w / 2
    ty = anchor[1] - h / 2
    draw_mixed_text(image, tx, ty, text, font, color, emoji=emoji, verbose=verbose)

def draw_poi_marker(image, x, y, caption=None, font=None, color=(30, 100, 240), shape="square", font_color=None, width=2, emoji=True, icon_size=20, verbose=False):
    draw = ImageDraw.Draw(image)
    shape_key = str(shape or "square").strip()

    if shape_key.lower() in SHAPES:
        draw_marker_shape(draw, x, y, shape=shape_key.lower(), color=color, radius=4, width=width)
    else:
        icon_font = load_caption_font(icon_size, verbose=verbose)
        icon_w, icon_h = measure_mixed_text(image, shape_key, icon_font, emoji=emoji, verbose=verbose)
        draw_mixed_text(image, x - icon_w / 2, y - icon_h / 2, shape_key, icon_font, color, emoji=emoji, verbose=verbose)

    if caption:
        if font_color is None:
            font_color = color
        text_y = y + 4 + 3
        text_w, _ = measure_mixed_text(image, caption, font, emoji=emoji, verbose=verbose)
        text_x = x - (text_w / 2)
        draw_mixed_text(image, text_x, text_y, caption, font, font_color, emoji=emoji, verbose=verbose)

SHAPE_TYPES = ("circle", "rect", "poly")
FILL_STYLES = ("solid", "hatch", "cross", "none")

def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))

def km_to_pixels(km, lat_deg, zoom):
    meters_per_pixel = 156543.03392804097 * math.cos(math.radians(lat_deg)) / (2 ** zoom)
    if meters_per_pixel <= 0:
        return 0
    return (km * 1000.0) / meters_per_pixel

def rotate_point(x, y, cx, cy, angle_deg):
    if not angle_deg:
        return (x, y)
    a = math.radians(angle_deg)
    dx, dy = x - cx, y - cy
    rx = cx + dx * math.cos(a) - dy * math.sin(a)
    ry = cy + dx * math.sin(a) + dy * math.cos(a)
    return (rx, ry)

def circle_sample_points(cx, cy, r, n=72):
    return [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)]

def fill_shape_region(image, kind, geom, fill_color, fill_style, opacity=1.0, fill_background=None):
    if fill_color is None or fill_style == "none":
        return

    opacity = max(0.0, min(1.0, opacity))
    if opacity == 0.0:
        return

    w, h = image.size
    shape_mask = Image.new("L", (w, h), 0)
    smdraw = ImageDraw.Draw(shape_mask)
    if kind == "circle":
        cx, cy, r = geom
        smdraw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)
    else:
        smdraw.polygon(geom, fill=255)

    if fill_style == "solid":
        alpha_mask = shape_mask.point(lambda p: int(p * opacity))
        color_layer = Image.new("RGB", (w, h), fill_color)
        image.paste(color_layer, (0, 0), mask=alpha_mask)
        return

    if fill_background is not None:
        bg_mask = shape_mask.point(lambda p: int(p * opacity))
        bg_layer = Image.new("RGB", (w, h), fill_background)
        image.paste(bg_layer, (0, 0), mask=bg_mask)

    pattern_alpha = Image.new("L", (w, h), 0)
    pattern = Image.new("RGB", (w, h), (0, 0, 0))
    padraw = ImageDraw.Draw(pattern_alpha)
    pdraw = ImageDraw.Draw(pattern)
    spacing = 8
    for offset in range(-h, w + h, spacing):
        pdraw.line([(offset, 0), (offset + h, h)], fill=fill_color, width=1)
        padraw.line([(offset, 0), (offset + h, h)], fill=255, width=1)
    if fill_style == "cross":
        for offset in range(-h, w + h, spacing):
            pdraw.line([(offset, h), (offset + h, 0)], fill=fill_color, width=1)
            padraw.line([(offset, h), (offset + h, 0)], fill=255, width=1)

    combined_mask = ImageChops.darker(pattern_alpha, shape_mask)
    if opacity < 1.0:
        combined_mask = combined_mask.point(lambda p: int(p * opacity))
    image.paste(pattern, (0, 0), mask=combined_mask)

def draw_shape_outline(draw, points, color, width, style, closed=True):
    pts = list(points)
    if closed and pts:
        pts = pts + [pts[0]]
    if len(pts) >= 2:
        draw_styled_line(draw, pts, color=color, width=width, style=style)

def resolve_point(entry, marker_lookup):
    if isinstance(entry, str):
        return marker_lookup.get(entry)
    if isinstance(entry, dict):
        if "lat" in entry and "lon" in entry:
            return (entry["lat"], entry["lon"])
        if "id" in entry:
            return marker_lookup.get(entry["id"])
        return None
    if isinstance(entry, (list, tuple)) and len(entry) >= 2:
        return (entry[0], entry[1])
    return None

def generate_map_by_size(lat, lon, zoom, width_px, height_px, provider_name, server_url, add_marker=False, write_cache=False, verbose=False, markers=None, marker_shape="square", marker_color=(255, 0, 0), lines=None, marker_defaults=None, line_defaults=None, shapes=None, shape_defaults=None, emoji=True):
    marker_defaults = marker_defaults or {}
    line_defaults = line_defaults or {}
    shape_defaults = shape_defaults or {}
    tile_size = 256
    center_tile_x, center_tile_y = lat_lon_to_tile_fractional(lat, lon, zoom)

    center_pixel_x = center_tile_x * tile_size
    center_pixel_y = center_tile_y * tile_size

    start_pixel_x = center_pixel_x - (width_px / 2)
    start_pixel_y = center_pixel_y - (height_px / 2)

    tile_start_x = math.floor(start_pixel_x / tile_size)
    tile_start_y = math.floor(start_pixel_y / tile_size)

    end_pixel_x = center_pixel_x + (width_px / 2)
    end_pixel_y = center_pixel_y + (height_px / 2)

    tile_end_x = math.ceil(end_pixel_x / tile_size)
    tile_end_y = math.ceil(end_pixel_y / tile_size)

    temp_image = Image.new("RGB", ((tile_end_x - tile_start_x) * tile_size, (tile_end_y - tile_start_y) * tile_size), (220, 220, 220))

    tiles_loaded = 0
    sd = 0 # index for current subdomain
    for x in range(tile_start_x, tile_end_x):
        for y in range(tile_start_y, tile_end_y):
            tile_img = get_tile_image(provider_name, SUBDOMAINS[sd], zoom, x, y, server_url, write_cache, verbose)
            sd = (sd + 1)%SDNB
            if tile_img:
                tiles_loaded += 1
                pos_x = (x - tile_start_x) * tile_size
                pos_y = (y - tile_start_y) * tile_size
                temp_image.paste(tile_img, (pos_x, pos_y))

    if tiles_loaded == 0 and verbose:
        print("[Info] No tile.", file=sys.stderr)

    crop_left = int(start_pixel_x - (tile_start_x * tile_size))
    crop_top = int(start_pixel_y - (tile_start_y * tile_size))
    final_image = temp_image.crop((crop_left, crop_top, crop_left + width_px, crop_top + height_px))

    if add_marker:
        draw = ImageDraw.Draw(final_image)
        cx, cy = width_px // 2, height_px // 2
        draw_marker_shape(draw, cx, cy, shape=marker_shape, color=marker_color, radius=4, width=2)

    def to_local_pixel(lat_, lon_):
        tx, ty = lat_lon_to_tile_fractional(lat_, lon_, zoom)
        return tx * tile_size - start_pixel_x, ty * tile_size - start_pixel_y

    marker_lookup = {}
    if markers:
        for node in markers:
            if not isinstance(node, dict):
                continue
            m_id = node.get("id") or node.get("caption")
            if m_id:
                marker_lookup[m_id] = (node.get("lat", lat), node.get("lon", lon))

    font_cache = {}

    if shapes:
        draw = ImageDraw.Draw(final_image)
        for shp in shapes:
            if not isinstance(shp, dict):
                if verbose:
                    print(f"[Shapes] Skipping malformed entry: {shp}", file=sys.stderr)
                continue

            kind = str(resolve_field(shp, shape_defaults, "type", "")).lower()
            if kind not in SHAPE_TYPES:
                if verbose:
                    print(f"[Shapes] Skipping entry with unknown/missing type: {shp}", file=sys.stderr)
                continue

            s_color = parse_color(resolve_field(shp, shape_defaults, "color", None), (0, 0, 0))
            s_width = resolve_field(shp, shape_defaults, "width", 2)
            s_line_style = str(resolve_field(shp, shape_defaults, "line_style", "plain")).lower()
            fill_raw = resolve_field(shp, shape_defaults, "fill", None)
            if fill_raw is not None:
                s_fill = parse_color(fill_raw, None)
                s_fill_style = str(resolve_field(shp, shape_defaults, "fill_style", "solid")).lower()
                s_opacity = resolve_field(shp, shape_defaults, "opacity", 1.0)
                fill_bg_raw = resolve_field(shp, shape_defaults, "fill_background", None)
                s_fill_background = parse_color(fill_bg_raw, None) if fill_bg_raw is not None else None
            else:
                s_fill = None
                s_fill_style = "none"
                s_opacity = 1.0
                s_fill_background = None

            if kind == "circle":
                center_entry = shp.get("center")
                radius_km = shp.get("radius_km")
                point_entry = shp.get("point")
                pts_entry = shp.get("points")

                center_ll = resolve_point(center_entry, marker_lookup) if center_entry is not None else None

                if center_ll is not None and radius_km is not None:
                    r_km = radius_km
                elif center_ll is not None and point_entry is not None:
                    edge_ll = resolve_point(point_entry, marker_lookup)
                    if edge_ll is None:
                        if verbose:
                            print(f"[Shapes] Could not resolve circle 'point': {shp}", file=sys.stderr)
                        continue
                    r_km = haversine_km(center_ll[0], center_ll[1], edge_ll[0], edge_ll[1])
                elif center_ll is None and isinstance(pts_entry, list) and len(pts_entry) == 2:
                    p1_ll = resolve_point(pts_entry[0], marker_lookup)
                    p2_ll = resolve_point(pts_entry[1], marker_lookup)
                    if p1_ll is None or p2_ll is None:
                        if verbose:
                            print(f"[Shapes] Could not resolve circle 'points': {shp}", file=sys.stderr)
                        continue
                    center_ll = ((p1_ll[0] + p2_ll[0]) / 2, (p1_ll[1] + p2_ll[1]) / 2)
                    r_km = haversine_km(p1_ll[0], p1_ll[1], p2_ll[0], p2_ll[1]) / 2
                else:
                    if verbose:
                        print(f"[Shapes] Circle needs center+radius_km, center+point, or 2 points: {shp}", file=sys.stderr)
                    continue

                cx, cy = to_local_pixel(center_ll[0], center_ll[1])
                r_px = km_to_pixels(r_km, center_ll[0], zoom)

                if verbose:
                    print(f"[Shapes] Drawing circle at {center_ll}, r={r_km:.3f}km ({r_px:.1f}px)", file=sys.stderr)

                fill_shape_region(final_image, "circle", (cx, cy, r_px), s_fill, s_fill_style,
                                   opacity=s_opacity, fill_background=s_fill_background)
                if s_line_style == "plain":
                    draw.ellipse([cx - r_px, cy - r_px, cx + r_px, cy + r_px], outline=s_color, width=s_width)
                else:
                    draw_shape_outline(draw, circle_sample_points(cx, cy, r_px), s_color, s_width, s_line_style)

            elif kind == "rect":
                center_entry = shp.get("center")
                point_entry = shp.get("point")
                width_km = shp.get("width_km")
                height_km = shp.get("height_km")
                pts_entry = shp.get("points")
                angle = shp.get("angle") or 0

                center_ll = resolve_point(center_entry, marker_lookup) if center_entry is not None else None

                if center_ll is not None and point_entry is not None:
                    corner_ll = resolve_point(point_entry, marker_lookup)
                    if corner_ll is None:
                        if verbose:
                            print(f"[Shapes] Could not resolve rect 'point': {shp}", file=sys.stderr)
                        continue
                    ccx, ccy = to_local_pixel(center_ll[0], center_ll[1])
                    pcx, pcy = to_local_pixel(corner_ll[0], corner_ll[1])
                    half_w, half_h = abs(pcx - ccx), abs(pcy - ccy)
                elif center_ll is not None and (width_km is not None or height_km is not None):
                    ccx, ccy = to_local_pixel(center_ll[0], center_ll[1])
                    half_w = km_to_pixels(width_km or 0, center_ll[0], zoom) / 2
                    half_h = km_to_pixels(height_km or 0, center_ll[0], zoom) / 2
                elif center_ll is None and isinstance(pts_entry, list) and len(pts_entry) == 2:
                    p1_ll = resolve_point(pts_entry[0], marker_lookup)
                    p2_ll = resolve_point(pts_entry[1], marker_lookup)
                    if p1_ll is None or p2_ll is None:
                        if verbose:
                            print(f"[Shapes] Could not resolve rect 'points': {shp}", file=sys.stderr)
                        continue
                    p1x, p1y = to_local_pixel(p1_ll[0], p1_ll[1])
                    p2x, p2y = to_local_pixel(p2_ll[0], p2_ll[1])
                    ccx, ccy = (p1x + p2x) / 2, (p1y + p2y) / 2
                    half_w, half_h = abs(p2x - p1x) / 2, abs(p2y - p1y) / 2
                else:
                    if verbose:
                        print(f"[Shapes] Rect needs center+point, center+width_km/height_km, "
                              f"or 2 points: {shp}", file=sys.stderr)
                    continue

                corners = [
                    (ccx - half_w, ccy - half_h), (ccx + half_w, ccy - half_h),
                    (ccx + half_w, ccy + half_h), (ccx - half_w, ccy + half_h),
                ]
                if angle:
                    corners = [rotate_point(px, py, ccx, ccy, angle) for px, py in corners]

                if verbose:
                    print(f"[Shapes] Drawing rect centered at pixel ({ccx:.1f},{ccy:.1f}), "
                          f"{half_w*2:.1f}x{half_h*2:.1f}px, angle={angle}", file=sys.stderr)

                fill_shape_region(final_image, "poly", corners, s_fill, s_fill_style,
                                   opacity=s_opacity, fill_background=s_fill_background)
                draw_shape_outline(draw, corners, s_color, s_width, s_line_style)

            elif kind == "poly":
                pts_entry = shp.get("points")
                if not isinstance(pts_entry, list) or len(pts_entry) < 3:
                    if verbose:
                        print(f"[Shapes] Poly needs at least 3 points: {shp}", file=sys.stderr)
                    continue
                poly_px = []
                for entry in pts_entry:
                    resolved = resolve_point(entry, marker_lookup)
                    if resolved is None:
                        if verbose:
                            print(f"[Shapes] Could not resolve poly point: {entry}", file=sys.stderr)
                        continue
                    poly_px.append(to_local_pixel(resolved[0], resolved[1]))
                if len(poly_px) < 3:
                    if verbose:
                        print(f"[Shapes] Skipping poly, fewer than 3 resolvable points: {shp}", file=sys.stderr)
                    continue

                if verbose:
                    print(f"[Shapes] Drawing poly with {len(poly_px)} points", file=sys.stderr)

                fill_shape_region(final_image, "poly", poly_px, s_fill, s_fill_style,
                                   opacity=s_opacity, fill_background=s_fill_background)
                draw_shape_outline(draw, poly_px, s_color, s_width, s_line_style)

    if lines:
        draw = ImageDraw.Draw(final_image)
        for art in lines:
            raw_points = art.get("points") if isinstance(art, dict) else None
            if not raw_points or len(raw_points) < 2:
                if verbose:
                    print(f"[Lines] Skipping entry with fewer than 2 points: {art}", file=sys.stderr)
                continue

            pixel_points = []
            for entry in raw_points:
                resolved = resolve_point(entry, marker_lookup)
                if resolved is None:
                    if verbose:
                        print(f"[Lines] Could not resolve point: {entry}", file=sys.stderr)
                    continue
                pixel_points.append(to_local_pixel(resolved[0], resolved[1]))

            if len(pixel_points) < 2:
                if verbose:
                    print(f"[Lines] Skipping entry, fewer than 2 resolvable points: {art}", file=sys.stderr)
                continue

            a_color = parse_color(resolve_field(art, line_defaults, "color", None), (0, 0, 0))
            a_width = resolve_field(art, line_defaults, "width", 2)
            a_style = resolve_field(art, line_defaults, "type", "plain")
            a_curve = str(resolve_field(art, line_defaults, "curve", "straight")).lower()
            a_arrow = str(resolve_field(art, line_defaults, "arrow", "")).lower()

            if a_curve == "bezier":
                pixel_points = smooth_path(pixel_points)

            if verbose:
                print(f"[Lines] Drawing {a_curve} {a_style} {'line' if len(raw_points) == 2 else 'path'} "
                      f"({len(raw_points)} points)", file=sys.stderr)
            draw_styled_line(draw, pixel_points, color=a_color, width=a_width, style=a_style)

            arrow_size = max(10, a_width * 3)
            if a_arrow in ("end", "both"):
                tip = pixel_points[-1]
                prev = pixel_points[-2]
                draw_arrowhead(draw, tip, (tip[0] - prev[0], tip[1] - prev[1]), a_color, size=arrow_size)
            if a_arrow in ("begin", "both"):
                tip = pixel_points[0]
                nxt = pixel_points[1]
                draw_arrowhead(draw, tip, (tip[0] - nxt[0], tip[1] - nxt[1]), a_color, size=arrow_size)

            text_defs = art.get("text")
            if isinstance(text_defs, dict):
                default_fractions = {"begin": 0.08, "middle": 0.5, "end": 0.92}
                for position, default_fraction in default_fractions.items():
                    label = text_defs.get(position)
                    if not isinstance(label, dict):
                        continue
                    label_text = label.get("text")
                    if not label_text:
                        continue

                    l_font_size = label.get("font_size") or 12
                    l_font_color = parse_color(label.get("font_color"), a_color)
                    side = str(label.get("side") or "left").lower()
                    fraction = label.get("position")
                    fraction = default_fraction if fraction is None else max(0.0, min(1.0, fraction))

                    anchor_point, tangent = point_and_tangent_at(pixel_points, fraction)
                    ux, uy = normalize(*tangent)
                    perp = (uy, -ux) if side == "right" else (-uy, ux)
                    offset = l_font_size + 6
                    anchor = (anchor_point[0] + perp[0] * offset, anchor_point[1] + perp[1] * offset)

                    label_font = font_cache.setdefault(l_font_size, load_caption_font(l_font_size, verbose=verbose))
                    if verbose:
                        print(f"[Lines] Drawing '{label_text}' at {position} "
                              f"(position={fraction}, side={side})", file=sys.stderr)
                    draw_line_label(final_image, anchor, label_font, label_text, l_font_color, emoji=emoji, verbose=verbose)

    if markers:
        draw = ImageDraw.Draw(final_image)
        for node in markers:
            if not isinstance(node, dict):
                if verbose:
                    print(f"[Markers] Skipping malformed entry: {node}", file=sys.stderr)
                continue

            m_lat = node.get("lat", lat)
            m_lon = node.get("lon", lon)
            caption = node.get("caption", "")

            if resolve_field(node, marker_defaults, "hide", False):
                if verbose:
                    print(f"[Markers] '{caption}' is hidden, not drawing", file=sys.stderr)
                continue

            m_color = parse_color(resolve_field(node, marker_defaults, "color", None), (30, 100, 240))
            m_shape = resolve_field(node, marker_defaults, "shape", "square")
            m_font_color = parse_color(resolve_field(node, marker_defaults, "font_color", None), m_color)
            m_font_size = resolve_field(node, marker_defaults, "font_size", 12)
            m_width = resolve_field(node, marker_defaults, "width", 2)
            m_icon_size = resolve_field(node, marker_defaults, "icon_size", 20)
            font = font_cache.setdefault(m_font_size, load_caption_font(m_font_size, verbose=verbose))

            m_tile_x, m_tile_y = lat_lon_to_tile_fractional(m_lat, m_lon, zoom)
            m_pixel_x = m_tile_x * tile_size
            m_pixel_y = m_tile_y * tile_size

            local_x = m_pixel_x - start_pixel_x
            local_y = m_pixel_y - start_pixel_y

            if 0 <= local_x <= width_px and 0 <= local_y <= height_px:
                if verbose:
                    print(f"[Markers] Placing '{caption}' at {m_lat},{m_lon}", file=sys.stderr)
                draw_poi_marker(final_image, local_x, local_y, caption=caption, font=font,
                                 color=m_color, shape=m_shape, font_color=m_font_color, width=m_width,
                                 emoji=emoji, icon_size=m_icon_size, verbose=verbose)
            else:
                if verbose:
                    print(f"[Markers] '{caption}' at {m_lat},{m_lon} is outside the map, skipping", file=sys.stderr)

    return final_image

def display_sixel_via_system(image, zoom=1):
    png_buffer = BytesIO()
    if zoom != 1.0:
        image = image.resize((int(image.size[0]*zoom), int(image.size[1]*zoom)),
                         Image.Resampling.LANCZOS)
    image.save(png_buffer, format="PNG")
    try:
        result = subprocess.run(['img2sixel'],
                       input=png_buffer.getvalue(),
                       capture_output=False,
                       check=False)
    except FileNotFoundError:
        print("\n[Error] 'img2sixel' missing.", file=sys.stderr)
        sys.exit(1)

JSON_HELP_TEXT = """\
coords2img reads an optional JSON document from stdin (whenever stdin isn't
an interactive terminal), from a -i/--input file, or via -J. It can take two
shapes:

1) A plain array of POIs:

   [
     {"lat": 47.75, "lon": -3.40, "caption": "Lorient"},
     {"lat": 47.39, "lon": -4.49, "caption": "Brest"}
   ]

2) An object of app parameters, with the POI array under "markers", and
   optional "lines" and "shapes" arrays:

   {
     "lat": 47.74792, "lon": -3.396558, "zoom": 12, "width": 600, "height": 400,
     "output": "map.png", "sixel": false, "marker": true,
     "provider": "opentopo", "custom_url": null, "zoom_factor": 1.0,
     "marker_shape": "square", "marker_color": "red",

     "marker_defaults": { ... },
     "line_defaults": { ... },
     "shape_defaults": { ... },
     "markers": [ ... ],
     "lines": [ ... ],
     "shapes": [ ... ]
   }

   Top-level keys include command-line parameters and will be overwritten
   if set on the command line.

MARKER_DEFAULTS / LINE_DEFAULTS / SHAPE_DEFAULTS: objects with the same
fields as an individual marker/line/shape entry (see below), used as
fallback values for any field a given entry doesn't set itself.
Resolution order for each field is: the entry's own value, then
marker_defaults/line_defaults/shape_defaults, then the hardcoded default
listed below.

MARKERS (each item in "markers"):
   lat, lon      optional -- a marker without coordinates uses the map's
                 center (lat/lon above)
   caption       text shown under the marker (default: "")
   id            identifier lines can reference (default: caption)
   hide          true to skip drawing this marker (still usable as a
                 line anchor point via its id) (default: false)
   color         marker color: name, "#rrggbb", "rgb(r,g,b)", or [r,g,b]
                 (default: blue)
   shape         "square", "circle", "cross", "diamond" -- or any other
                 string (typically a single emoji, e.g. "📍" or "🏠"),
                 which is drawn as the marker's icon itself instead of a
                 geometric shape (default: square)
   width         outline stroke width in px, only used for the built-in
                 geometric shapes (default: 2)
   icon_size     size in px of a custom glyph/emoji shape (default: 20)
   font_color    caption color (default: same as color)
   font_size     caption font size in px (default: 12)

   Markers outside the generated map's bounds are silently skipped.

   Captions (and line text labels below) can contain emoji -- they're
   rendered in color using a system emoji font if one is found (e.g.
   Noto Color Emoji on Linux). Without one, emoji characters are drawn
   with the regular caption font and typically show as blank/placeholder
   glyphs, same as any app without emoji font support. Set the top-level
   "emoji" key to false (or pass --no-emoji) to always draw them with the
   regular font instead.

LINES (each item in "lines"): lines between two points, or paths
across several points.
   points   required, list of 2+ entries. Each entry is either:
              - a marker "id" (string)
              - a {"lat": ..., "lon": ...} or {"id": ...} object
              - a plain [lat, lon] pair
            2 points draws a line, 3+ draws a path.
   color    same formats as marker color (default: black)
   width    stroke width in px (default: 2)
   type     "plain", "dotted", or "dash" (default: plain)
   curve    "straight" or "bezier" -- bezier smooths a multi-point path
            through all points via a Catmull-Rom spline (default: straight)
   arrow    "begin", "end", or "both" -- draws an arrowhead at the start
            and/or end of the line/path (default: none)
   text     optional object with up to 3 keys -- "begin", "middle", "end"
            -- each a label placed at that point along the line/path
            (by arc length, so "middle" is the true midpoint of a curve):
              text        the label string (required to draw anything)
              position    fraction 0.0-1.0 along the line/path, overriding
                           the key's default (default: 0.08 for "begin",
                           0.5 for "middle", 0.92 for "end"
              side        "left" or "right" of the line's direction of
                           travel at that point (default: left)
              font_size   label font size in px (default: 12)
              font_color  label color (default: same as the line's color)

SHAPES (each item in "shapes"): circles, rectangles, and free-form
polygons, with an optional fill.
   type          required: "circle", "rect", or "poly"
   color         outline color (default: black)
   width         outline stroke width in px (default: 2)
   line_style    "plain", "dotted", or "dash" (default: plain)
   fill          fill color -- omit for no fill (default: none)
   fill_style    "solid", "hatch", or "cross" (default: solid, only
                 matters if "fill" is set)
   opacity       0.0-1.0, blends the fill with what's underneath (only
                 matters if "fill" is set; default: 1.0 = fully opaque)
   fill_background  solid backdrop color drawn behind the hatch/cross
                 lines (only used when fill_style is "hatch"/"cross";
                 default: none, so the map shows through the gaps
                 between lines instead of a solid backdrop)

   circle -- built one of three ways:
     center + radius_km            {"center": ..., "radius_km": 2.5}
     center + point (radius = real-world distance center->point)
                                    {"center": ..., "point": ...}
     2 points (as the diameter's endpoints, no "center" needed)
                                    {"points": [p1, p2]}

   rect -- built one of three ways, plus an optional "angle" (degrees,
   rotates the rectangle around its center; default: 0):
     center + point (one corner; axis-aligned rectangle)
                                    {"center": ..., "point": ...}
     center + width_km/height_km   {"center": ..., "width_km": 3, "height_km": 1.5}
     2 points (diagonal corners, axis-aligned before rotation)
                                    {"points": [p1, p2]}

   poly -- a free-form polygon:
     points   required, list of 3+ entries (same point formats as lines)

   In all of the above, a "point"/"center"/list entry in "points" can be
   a marker "id" (string), a {"lat":..., "lon":...}/{"id":...} object, or
   a plain [lat, lon] pair -- exactly like a line's "points".

EXAMPLE combining everything:

   {
     "zoom": 13, "marker_shape": "diamond", "marker_color": "purple",
     "marker_defaults": {"shape": "circle", "color": "green"},
     "line_defaults": {"type": "dash", "width": 3},
     "markers": [
       {"id": "A", "lat": 47.752, "lon": -3.402, "caption": "Start"},
       {"id": "B", "lat": 47.746, "lon": -3.394, "caption": "End", "shape": "diamond"},
       {"id": "W", "lat": 47.749, "lon": -3.410, "hide": true}
     ],
     "lines": [
       {"points": ["A", "W", "B"], "color": "blue", "curve": "bezier",
        "text": {"middle": {"text": "3.2 km", "side": "right"}}},
       {"points": ["A", "B"]}
     ],
     "shapes": [
       {"type": "circle", "center": "A", "radius_km": 1, "fill": "green", "fill_style": "hatch", "opacity": 0.6},
       {"type": "rect", "points": ["A", "B"], "angle": 15, "color": "orange"}
     ]
   }
"""

DEFAULTS = {
    "lat": 47.74792,
    "lon": -3.396558,
    "zoom": 12,
    "width": 600,
    "height": 400,
    "output": None,
    "sixel": False,
    "marker": False,
    "provider": "opentopo",
    "custom_url": None,
    "zoom_factor": 1.0,
    "marker_shape": "square",
    "marker_color": "red",
    "emoji": True,
}

def main():
    parser = argparse.ArgumentParser(description="Map image generator.")
    parser.add_argument("-y", "--lat", type=float, default=None, help="latitude in °")
    parser.add_argument("-x", "--lon", type=float, default=None, help="longitude in °")
    parser.add_argument("-z", "--zoom", type=int, default=None, help="zoom at which tiles are downloaded")
    parser.add_argument("-W", "--width", type=int, default=None, help="width in pixels")
    parser.add_argument("-H", "--height", type=int, default=None, help="height in pixels")
    parser.add_argument("-i", "--input", type=str, default=None, help="use file instead of stdin")
    parser.add_argument("-o", "--output", type=str, default=None, help="output to a given file")
    parser.add_argument("-s", "--sixel", action=argparse.BooleanOptionalAction, default=None, help="display in terminal via sixel")
    parser.add_argument("-m", "--marker", action=argparse.BooleanOptionalAction, default=None, help="display marker for position")
    parser.add_argument("-v", "--verbose", action="store_true", help="verbose output")
    parser.add_argument("-p", "--provider", type=str, choices=list(MAP_SERVERS.keys()), default=None)
    parser.add_argument("-u", "--custom-url", type=str, default=None)
    parser.add_argument("-f", "--zoom-factor", type=float, default=None, help="zoom applied before displaying in terminal")
    parser.add_argument("-J", "--markers-stdin", action="store_true", help="force reading JSON from stdin")
    parser.add_argument("--emoji", action=argparse.BooleanOptionalAction, default=None,
                         help="render emoji in captions/labels (default: on; use --no-emoji to disable)")
    parser.add_argument("--help-json", action="store_true",
                         help="print a detailed explanation of the JSON input format and exit")

    args = parser.parse_args()

    if args.help_json:
        print(JSON_HELP_TEXT)
        sys.exit(0)

    json_params = {}
    markers = None
    lines = None
    marker_defaults = {}
    line_defaults = {}
    shapes = None
    shape_defaults = {}

    raw = None
    if args.input:
        try:
            with open(args.input, "r") as f:
                raw = f.read()
        except OSError as e:
            print(f"[Error] Could not read input file '{args.input}': {e}", file=sys.stderr)
            sys.exit(1)
    elif args.markers_stdin or not sys.stdin.isatty():
        raw = sys.stdin.read()

    if raw is not None:
        if not raw.strip():
            data = []
        else:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as e:
                print(f"[Error] Invalid JSON: {e}", file=sys.stderr)
                sys.exit(1)

        if isinstance(data, list):
            markers = data
        elif isinstance(data, dict):
            markers = data.get("markers", [])
            if not isinstance(markers, list):
                print("[Error] The 'markers' key must contain an array of POI objects.", file=sys.stderr)
                sys.exit(1)
            lines = data.get("lines", [])
            if not isinstance(lines, list):
                print("[Error] The 'lines' key must contain an array of line/path objects.", file=sys.stderr)
                sys.exit(1)
            marker_defaults = data.get("marker_defaults", {})
            if not isinstance(marker_defaults, dict):
                print("[Error] The 'marker_defaults' key must be an object.", file=sys.stderr)
                sys.exit(1)
            line_defaults = data.get("line_defaults", {})
            if not isinstance(line_defaults, dict):
                print("[Error] The 'line_defaults' key must be an object.", file=sys.stderr)
                sys.exit(1)
            shapes = data.get("shapes", [])
            if not isinstance(shapes, list):
                print("[Error] The 'shapes' key must contain an array of shape objects.", file=sys.stderr)
                sys.exit(1)
            shape_defaults = data.get("shape_defaults", {})
            if not isinstance(shape_defaults, dict):
                print("[Error] The 'shape_defaults' key must be an object.", file=sys.stderr)
                sys.exit(1)
            json_params = {k: v for k, v in data.items()
                            if k not in ("markers", "lines", "marker_defaults", "line_defaults",
                                         "shapes", "shape_defaults")}
        else:
            print("[Error] JSON input must be either an array of POIs or an object of parameters.", file=sys.stderr)
            sys.exit(1)

    cfg = {}
    for key, default in DEFAULTS.items():
        cli_val = getattr(args, key, None)
        if cli_val is not None:
            cfg[key] = cli_val
        elif key in json_params:
            cfg[key] = json_params[key]
        else:
            cfg[key] = default

    if not cfg["output"] and not cfg["sixel"]:
        parser.print_help(sys.stderr)
        sys.exit(1)

    os.makedirs(CACHE_DIR, exist_ok=True)
    if args.verbose:
        print(f"[System] Cache dir active : {CACHE_DIR}", file=sys.stderr)

    provider_id = "custom" if cfg["custom_url"] else cfg["provider"]
    if not cfg["custom_url"] and cfg["provider"] not in MAP_SERVERS:
        print(f"[Error] Unknown provider '{cfg['provider']}'. Choices: {', '.join(MAP_SERVERS.keys())}", file=sys.stderr)
        sys.exit(1)
    selected_url = cfg["custom_url"] if cfg["custom_url"] else MAP_SERVERS[cfg["provider"]]

    img = generate_map_by_size(
        lat=cfg["lat"], lon=cfg["lon"], zoom=cfg["zoom"], width_px=cfg["width"], height_px=cfg["height"],
        provider_name=provider_id, server_url=selected_url, add_marker=cfg["marker"],
        write_cache=True, verbose=args.verbose, markers=markers,
        marker_shape=cfg["marker_shape"], marker_color=parse_color(cfg["marker_color"], (255, 0, 0)),
        lines=lines, marker_defaults=marker_defaults, line_defaults=line_defaults,
        shapes=shapes, shape_defaults=shape_defaults, emoji=cfg["emoji"]
    )

    if cfg["output"]:
        img.save(cfg["output"], "PNG")
        if args.verbose:
            print(f"[System] Saved : {cfg['output']}")

    if cfg["sixel"]:
        display_sixel_via_system(img, cfg["zoom_factor"])

if __name__ == "__main__":
    main()
