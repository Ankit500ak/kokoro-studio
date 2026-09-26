"""
Thumbnail Engine v2
Professional YouTube thumbnail generation with Pillow + FFmpeg.
Optimized for maximum click-through rate.
"""
import logging
import math
import os
import subprocess
import tempfile

log = logging.getLogger(__name__)

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

OUTPUT_SIZE = (1280, 720)

NICHE_STYLES = {
    "true_crime": {
        "bg_brightness": 0.35, "bg_color": 0.5, "contrast": 1.5, "vignette": 0.8,
        "title_color": (255, 50, 50), "title_stroke": (0, 0, 0),
        "accent_color": (255, 0, 0), "accent_glow": (255, 50, 0),
        "gradient_top": (0, 0, 0, 0), "gradient_bottom": (0, 0, 0, 220),
        "font_size": 72, "stroke_width": 4, "glow_radius": 8, "pattern": "diagonal",
    },
    "psychology": {
        "bg_brightness": 0.5, "bg_color": 0.6, "contrast": 1.2, "vignette": 0.5,
        "title_color": (255, 255, 255), "title_stroke": (40, 20, 80),
        "accent_color": (180, 100, 255), "accent_glow": (150, 80, 255),
        "gradient_top": (30, 15, 60, 0), "gradient_bottom": (30, 15, 60, 200),
        "font_size": 68, "stroke_width": 4, "glow_radius": 7, "pattern": "dots",
    },
    "tech_tips": {
        "bg_brightness": 0.45, "bg_color": 0.9, "contrast": 1.3, "vignette": 0.35,
        "title_color": (0, 255, 200), "title_stroke": (0, 50, 80),
        "accent_color": (0, 230, 255), "accent_glow": (0, 200, 255),
        "gradient_top": (0, 15, 30, 0), "gradient_bottom": (0, 15, 30, 190),
        "font_size": 66, "stroke_width": 4, "glow_radius": 6, "pattern": "grid",
    },
    "finance": {
        "bg_brightness": 0.4, "bg_color": 0.8, "contrast": 1.5, "vignette": 0.5,
        "title_color": (0, 255, 100), "title_stroke": (0, 50, 20),
        "accent_color": (0, 220, 120), "accent_glow": (0, 200, 100),
        "gradient_top": (0, 20, 10, 0), "gradient_bottom": (0, 20, 10, 200),
        "font_size": 70, "stroke_width": 4, "glow_radius": 7, "pattern": "lines",
    },
    "science": {
        "bg_brightness": 0.4, "bg_color": 0.7, "contrast": 1.25, "vignette": 0.45,
        "title_color": (255, 255, 255), "title_stroke": (10, 30, 80),
        "accent_color": (100, 180, 255), "accent_glow": (80, 150, 255),
        "gradient_top": (10, 20, 50, 0), "gradient_bottom": (10, 20, 50, 190),
        "font_size": 68, "stroke_width": 4, "glow_radius": 7, "pattern": "circles",
    },
    "history": {
        "bg_brightness": 0.45, "bg_color": 0.4, "contrast": 1.2, "vignette": 0.75,
        "title_color": (255, 220, 80), "title_stroke": (60, 30, 0),
        "accent_color": (255, 200, 50), "accent_glow": (255, 180, 0),
        "gradient_top": (40, 20, 0, 0), "gradient_bottom": (40, 20, 0, 200),
        "font_size": 70, "stroke_width": 4, "glow_radius": 7, "pattern": "vintage",
    },
    "motivation": {
        "bg_brightness": 0.35, "bg_color": 0.8, "contrast": 1.5, "vignette": 0.45,
        "title_color": (255, 255, 255), "title_stroke": (40, 20, 0),
        "accent_color": (255, 120, 0), "accent_glow": (255, 100, 0),
        "gradient_top": (30, 15, 0, 0), "gradient_bottom": (30, 15, 0, 200),
        "font_size": 74, "stroke_width": 5, "glow_radius": 8, "pattern": "burst",
    },
    "horror": {
        "bg_brightness": 0.25, "bg_color": 0.4, "contrast": 1.5, "vignette": 0.9,
        "title_color": (255, 0, 0), "title_stroke": (0, 0, 0),
        "accent_color": (200, 0, 0), "accent_glow": (180, 0, 0),
        "gradient_top": (15, 0, 0, 0), "gradient_bottom": (15, 0, 0, 220),
        "font_size": 72, "stroke_width": 4, "glow_radius": 10, "pattern": "scratches",
    },
    "philosophy": {
        "bg_brightness": 0.5, "bg_color": 0.5, "contrast": 1.15, "vignette": 0.6,
        "title_color": (240, 240, 255), "title_stroke": (30, 30, 60),
        "accent_color": (160, 120, 255), "accent_glow": (140, 100, 255),
        "gradient_top": (20, 20, 40, 0), "gradient_bottom": (20, 20, 40, 190),
        "font_size": 66, "stroke_width": 4, "glow_radius": 7, "pattern": "dots",
    },
    "nature": {
        "bg_brightness": 0.5, "bg_color": 1.0, "contrast": 1.25, "vignette": 0.35,
        "title_color": (255, 255, 255), "title_stroke": (10, 40, 15),
        "accent_color": (50, 200, 100), "accent_glow": (40, 180, 80),
        "gradient_top": (5, 20, 8, 0), "gradient_bottom": (5, 20, 8, 180),
        "font_size": 70, "stroke_width": 4, "glow_radius": 7, "pattern": "leaves",
    },
}


def _get_font(size, bold=True):
    import platform
    system = platform.system()
    
    if bold:
        if system == "Windows":
            paths = ["C:/Windows/Fonts/impact.ttf", "C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/calibrib.ttf"]
        elif system == "Darwin":  # macOS
            paths = [
                "/Library/Fonts/Arial Bold.ttf",
                "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                "/Library/Fonts/Impact.ttf",
                "/System/Library/Fonts/Helvetica.ttc",
            ]
        else:  # Linux
            paths = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
                "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/ubuntu/Ubuntu-Bold.ttf",
            ]
    else:
        if system == "Windows":
            paths = ["C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/segoeui.ttf"]
        elif system == "Darwin":
            paths = [
                "/Library/Fonts/Arial.ttf",
                "/System/Library/Fonts/Supplemental/Arial.ttf",
                "/System/Library/Fonts/Helvetica.ttc",
            ]
        else:
            paths = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                "/usr/share/fonts/TTF/DejaVuSans.ttf",
            ]
    
    for fp in paths:
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _extract_frame(video_path, time_sec=None):
    if not os.path.exists(video_path):
        return None
    if time_sec is None:
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", video_path],
                capture_output=True, text=True, timeout=15,
            )
            duration = float(result.stdout.strip() or "10")
            time_sec = duration * 0.30
        except Exception:
            time_sec = 2.0
    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    tmp.close()
    try:
        subprocess.run([
            "ffmpeg", "-y", "-i", video_path, "-ss", str(time_sec),
            "-vframes", "1",
            "-vf", f"scale={OUTPUT_SIZE[0]}:{OUTPUT_SIZE[1]}:force_original_aspect_ratio=increase,crop={OUTPUT_SIZE[0]}:{OUTPUT_SIZE[1]}",
            "-q:v", "2", tmp.name,
        ], capture_output=True, timeout=30)
        if os.path.exists(tmp.name) and os.path.getsize(tmp.name) > 0:
            return Image.open(tmp.name).convert("RGBA")
    except Exception as e:
        log.warning(f"[Thumbnail] Frame extraction failed: {e}")
    finally:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)
    return None


def _apply_gradient(img, top_color, bottom_color):
    w, h = img.size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for y in range(h):
        r = y / h
        c = tuple(int(top_color[i] + (bottom_color[i] - top_color[i]) * r) for i in range(4))
        draw.line([(0, y), (w, y)], fill=c)
    return Image.alpha_composite(img, overlay)


def _apply_vignette(img, strength):
    w, h = img.size
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    cx, cy = w // 2, h // 2
    max_r = math.sqrt(cx**2 + cy**2)
    for r in range(int(max_r), 0, -3):
        opacity = min(255, max(0, int(255 * (1 - (r / max_r)) ** 1.5 * strength)))
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=opacity)
    mask = mask.filter(ImageFilter.GaussianBlur(radius=10))
    vignette = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    return Image.composite(img, vignette, mask)


def _draw_text_stroke(draw, pos, text, font, fill, stroke_color, stroke_width=4):
    x, y = pos
    for dx in range(-stroke_width, stroke_width + 1):
        for dy in range(-stroke_width, stroke_width + 1):
            if dx * dx + dy * dy <= stroke_width * stroke_width and (dx != 0 or dy != 0):
                draw.text((x + dx, y + dy), text, font=font, fill=stroke_color)
    draw.text((x, y), text, font=font, fill=fill)


def _draw_glow(pos, text, font, glow_color, radius=7):
    x, y = pos
    glow = Image.new("RGBA", OUTPUT_SIZE, (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    for dx in range(-radius, radius + 1, 2):
        for dy in range(-radius, radius + 1, 2):
            d = math.sqrt(dx * dx + dy * dy)
            if d <= radius:
                a = int(100 * (1 - d / radius))
                gdraw.text((x + dx, y + dy), text, font=font, fill=(*glow_color, a))
    return glow.filter(ImageFilter.GaussianBlur(radius=radius))


def _wrap_text(text, font, max_width, max_lines=3):
    words = text.upper().split()
    lines, current = [], ""
    tmp = Image.new("RGB", (1, 1))
    d = ImageDraw.Draw(tmp)
    for word in words:
        test = f"{current} {word}".strip()
        bbox = d.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines[:max_lines]


def _draw_pattern(img, pattern, color):
    w, h = img.size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    r, g, b = color
    if pattern == "diagonal":
        for i in range(-h, w + h, 40):
            draw.line([(i, 0), (i + h, h)], fill=(r, g, b, 15), width=2)
    elif pattern == "dots":
        for x in range(0, w, 30):
            for y in range(0, h, 30):
                draw.ellipse([x - 2, y - 2, x + 2, y + 2], fill=(r, g, b, 20))
    elif pattern == "grid":
        for x in range(0, w, 50):
            draw.line([(x, 0), (x, h)], fill=(r, g, b, 12))
        for y in range(0, h, 50):
            draw.line([(0, y), (w, y)], fill=(r, g, b, 12))
    elif pattern == "circles":
        for x in range(0, w, 60):
            for y in range(0, h, 60):
                draw.ellipse([x - 15, y - 15, x + 15, y + 15], outline=(r, g, b, 15))
    elif pattern == "burst":
        cx, cy = w // 2, h // 2
        for angle in range(0, 360, 15):
            rad = math.radians(angle)
            ex = int(cx + math.cos(rad) * 500)
            ey = int(cy + math.sin(rad) * 500)
            draw.line([(cx, cy), (ex, ey)], fill=(r, g, b, 10), width=2)
    return Image.alpha_composite(img, overlay)


def _draw_accent(draw, style, w, h):
    accent = style["accent_color"]
    bar_h = 8
    for i in range(bar_h):
        a = 255 - int(i * (255 / bar_h))
        c = tuple(int(accent[j] * a / 255) for j in range(3))
        draw.line([(0, h - bar_h + i), (w, h - bar_h + i)], fill=c)
    draw.rectangle([0, 0, 6, h], fill=accent)
    draw.line([(0, 0), (w, 0)], fill=accent, width=3)
    cs = 30
    draw.polygon([(0, 0), (cs, 0), (0, cs)], fill=accent)
    draw.polygon([(w, 0), (w - cs, 0), (w, cs)], fill=accent)


def _draw_bottom_bar(draw, niche, w, h, style):
    bar_h = 40
    bar_y = h - bar_h
    for y in range(bar_y, h):
        draw.line([(0, y), (w, y)], fill=(0, 0, 0, 180))
    lf = _get_font(20, True)
    draw.text((20, bar_y + 10), niche.replace("_", " ").upper(), font=lf, fill=style["accent_color"])
    bf = _get_font(16, True)
    bt = "STORYTIME"
    bb = draw.textbbox((0, 0), bt, font=bf)
    bw = bb[2] - bb[0] + 20
    bx = w - bw - 20
    draw.rounded_rectangle([bx, bar_y + 8, bx + bw, bar_y + 32], radius=4, fill=style["accent_color"])
    draw.text((bx + 10, bar_y + 10), bt, font=bf, fill=(255, 255, 255))


def _draw_top_badge(draw, title, w, style):
    bf = _get_font(22, True)
    words = title.split()[:5]
    badge_text = " ".join(words).upper()[:40]
    bb = draw.textbbox((0, 0), badge_text, font=bf)
    bw = bb[2] - bb[0] + 30
    draw.rounded_rectangle([w // 2 - bw // 2, 15, w // 2 + bw // 2, 50], radius=6, fill=(*style["accent_color"], 200))
    draw.text((w // 2 - (bb[2] - bb[0]) // 2, 20), badge_text, font=bf, fill=(255, 255, 255))


def generate_thumbnail(video_path, title, niche, output_path, subtitle=None):
    if not HAS_PILLOW:
        return None
    style = NICHE_STYLES.get(niche, NICHE_STYLES["psychology"])
    frame = _extract_frame(video_path)
    if frame is None:
        frame = Image.new("RGBA", OUTPUT_SIZE, (20, 20, 30, 255))
    else:
        frame = frame.convert("RGBA")
    frame = frame.resize(OUTPUT_SIZE, Image.LANCZOS)
    frame = ImageEnhance.Brightness(frame.convert("RGB")).enhance(style["bg_brightness"]).convert("RGBA")
    frame = ImageEnhance.Contrast(frame.convert("RGB")).enhance(style["contrast"]).convert("RGBA")
    frame = ImageEnhance.Color(frame.convert("RGB")).enhance(style["bg_color"]).convert("RGBA")
    frame = _draw_pattern(frame, style["pattern"], style["accent_color"])
    frame = _apply_gradient(frame, style["gradient_top"], style["gradient_bottom"])
    frame = _apply_vignette(frame, style["vignette"])
    font = _get_font(style["font_size"], True)
    margin = 80
    max_tw = OUTPUT_SIZE[0] - margin * 2
    lines = _wrap_text(title, font, max_tw)
    lh = style["font_size"] + 14
    th = len(lines) * lh
    start_y = (OUTPUT_SIZE[1] - th) // 2 - 20
    glow_layer = Image.new("RGBA", OUTPUT_SIZE, (0, 0, 0, 0))
    for i, line in enumerate(lines):
        bb = ImageDraw.Draw(Image.new("RGB", (1, 1))).textbbox((0, 0), line, font=font)
        tw = bb[2] - bb[0]
        x = (OUTPUT_SIZE[0] - tw) // 2
        y = start_y + i * lh
        glow = _draw_glow((x, y), line, font, style["accent_glow"], style["glow_radius"])
        glow_layer = Image.alpha_composite(glow_layer, glow)
    frame = Image.alpha_composite(frame, glow_layer)
    draw = ImageDraw.Draw(frame)
    for i, line in enumerate(lines):
        bb = draw.textbbox((0, 0), line, font=font)
        tw = bb[2] - bb[0]
        x = (OUTPUT_SIZE[0] - tw) // 2
        y = start_y + i * lh
        _draw_text_stroke(draw, (x, y), line, font, style["title_color"], style["title_stroke"], style["stroke_width"])
    if subtitle:
        sf = _get_font(28, False)
        sb = draw.textbbox((0, 0), subtitle.upper(), font=sf)
        sw = sb[2] - sb[0]
        draw.text(((OUTPUT_SIZE[0] - sw) // 2, start_y + th + 25), subtitle.upper(), font=sf, fill=style["title_color"])
    _draw_accent(draw, style, OUTPUT_SIZE[0], OUTPUT_SIZE[1])
    _draw_bottom_bar(draw, niche, OUTPUT_SIZE[0], OUTPUT_SIZE[1], style)
    _draw_top_badge(draw, title, OUTPUT_SIZE[0], style)
    frame.convert("RGB").save(output_path, "JPEG", quality=95)
    log.info(f"[Thumbnail] Generated: {output_path}")
    return output_path
