"""Generate Bayora's presentation artwork backgrounds.

The artwork is intentionally generated from the existing cinematic mask
references instead of drawing people or masks as vector shapes.  Keep the
source images in ``src/bayora/static`` and run this file from any directory:

    PYTHONPATH=/tmp/omnirush/pptxlib/site python presentation/make_artwork.py

Only Pillow is required.  The default output is three 1920x1080 JPEGs in
``presentation/assets``.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageOps


WIDTH = 1920
HEIGHT = 1080
INK = (7, 11, 19)
CYAN = (100, 244, 208)
RED = (255, 83, 110)
BLUE = (87, 158, 255)

ROOT = Path(__file__).resolve().parents[1]
RED_REFERENCE = ROOT / "src" / "bayora" / "static" / "mask-red-reference.png"
BLUE_REFERENCE = ROOT / "src" / "bayora" / "static" / "mask-blue-reference.png"


def resize_to_width(image: Image.Image, width: int) -> Image.Image:
    """Resize a source without stretching its cinematic 16:9 composition."""

    height = round(image.height * width / image.width)
    return image.resize((width, height), Image.Resampling.LANCZOS)


def grade(image: Image.Image, *, contrast: float = 1.0, brightness: float = 1.0) -> Image.Image:
    """Make the references sit together as one darker presentation system."""

    image = image.convert("RGB")
    image = ImageEnhance.Contrast(image).enhance(contrast)
    image = ImageEnhance.Brightness(image).enhance(brightness)
    return image


def _smoothstep(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


def fade_mask(
    size: tuple[int, int],
    *,
    opacity: float = 1.0,
    left: float = 0.0,
    right: float = 0.0,
    top: float = 0.0,
    bottom: float = 0.0,
) -> Image.Image:
    """Build a feathered alpha mask for a photographic layer.

    The mask is made at a smaller working size and enlarged, which gives the
    joins between the source photographs a softer, more photographic edge.
    ``left``/``right``/``top``/``bottom`` are fade distances in local pixels.
    """

    width, height = size
    small_width = min(width, 640)
    small_height = max(1, round(height * small_width / width))
    values = bytearray(small_width * small_height)

    for y in range(small_height):
        source_y = y * height / max(1, small_height - 1)
        top_factor = 1.0 if not top else _smoothstep(source_y / top)
        bottom_factor = 1.0 if not bottom else _smoothstep((height - source_y) / bottom)
        for x in range(small_width):
            source_x = x * width / max(1, small_width - 1)
            left_factor = 1.0 if not left else _smoothstep(source_x / left)
            right_factor = 1.0 if not right else _smoothstep((width - source_x) / right)
            factor = max(0.0, min(1.0, top_factor * bottom_factor * left_factor * right_factor * opacity))
            values[y * small_width + x] = round(255 * factor)

    return Image.frombytes("L", (small_width, small_height), bytes(values)).resize(
        size, Image.Resampling.BICUBIC
    )


def paste_reference(
    canvas: Image.Image,
    source: Image.Image,
    xy: tuple[int, int],
    width: int,
    *,
    opacity: float = 1.0,
    left: float = 0.0,
    right: float = 0.0,
    top: float = 0.0,
    bottom: float = 0.0,
    contrast: float = 1.0,
    brightness: float = 1.0,
) -> None:
    """Resize, grade, feather, and paste a photographic reference."""

    image = resize_to_width(source, width)
    image = grade(image, contrast=contrast, brightness=brightness)
    mask = fade_mask(
        image.size,
        opacity=opacity,
        left=left,
        right=right,
        top=top,
        bottom=bottom,
    )
    canvas.paste(image, xy, mask)


def color_overlay(canvas: Image.Image, color: tuple[int, int, int], mask: Image.Image) -> None:
    """Apply a solid color through an L mask without changing the canvas mode."""

    canvas.paste(color, (0, 0, canvas.width, canvas.height), mask)


def horizontal_mask(
    size: tuple[int, int], stops: tuple[tuple[float, float], ...], *, power: float = 1.0
) -> Image.Image:
    """Create a horizontal grayscale ramp from ``(x, alpha)`` stops."""

    width, height = size
    small_width = min(width, 640)
    small_height = max(1, round(height * small_width / width))
    row = []
    for x in range(small_width):
        position = x * (width - 1) / max(1, small_width - 1)
        if position <= stops[0][0]:
            value = stops[0][1]
        elif position >= stops[-1][0]:
            value = stops[-1][1]
        else:
            for (x0, a0), (x1, a1) in zip(stops, stops[1:]):
                if x0 <= position <= x1:
                    amount = _smoothstep((position - x0) / max(1.0, x1 - x0))
                    value = a0 + (a1 - a0) * amount
                    break
        row.append(round(max(0.0, min(255.0, value)) ** power / (255 ** (power - 1)) if power else value))
    pixels = bytes(row * small_height)
    return Image.frombytes("L", (small_width, small_height), pixels).resize(size, Image.Resampling.BICUBIC)


def vertical_mask(
    size: tuple[int, int], stops: tuple[tuple[float, float], ...], *, power: float = 1.0
) -> Image.Image:
    """Create a vertical grayscale ramp from ``(y, alpha)`` stops."""

    width, height = size
    small_height = min(height, 360)
    small_width = max(1, round(width * small_height / height))
    column = []
    for y in range(small_height):
        position = y * (height - 1) / max(1, small_height - 1)
        if position <= stops[0][0]:
            value = stops[0][1]
        elif position >= stops[-1][0]:
            value = stops[-1][1]
        else:
            for (y0, a0), (y1, a1) in zip(stops, stops[1:]):
                if y0 <= position <= y1:
                    amount = _smoothstep((position - y0) / max(1.0, y1 - y0))
                    value = a0 + (a1 - a0) * amount
                    break
        column.append(round(max(0.0, min(255.0, value)) ** power / (255 ** (power - 1)) if power else value))
    small = Image.new("L", (small_width, small_height))
    small.putdata([value for value in column for _ in range(small_width)])
    return small.resize(size, Image.Resampling.BICUBIC)


def radial_mask(
    size: tuple[int, int],
    center: tuple[float, float],
    radius: tuple[float, float],
    *,
    strength: float = 255.0,
    exponent: float = 1.6,
) -> Image.Image:
    """Create a smooth elliptical alpha field for glows and vignettes."""

    width, height = size
    small_width = min(width, 480)
    small_height = max(1, round(height * small_width / width))
    values = bytearray(small_width * small_height)
    cx, cy = center
    rx, ry = radius
    for y in range(small_height):
        source_y = y * height / max(1, small_height - 1)
        for x in range(small_width):
            source_x = x * width / max(1, small_width - 1)
            distance = math.sqrt(((source_x - cx) / rx) ** 2 + ((source_y - cy) / ry) ** 2)
            factor = max(0.0, 1.0 - distance) ** exponent
            values[y * small_width + x] = round(max(0.0, min(255.0, strength * factor)))
    return Image.frombytes("L", (small_width, small_height), bytes(values)).resize(
        size, Image.Resampling.BICUBIC
    )


def soft_glow(
    canvas: Image.Image,
    center: tuple[float, float],
    radius: tuple[float, float],
    color: tuple[int, int, int],
    *,
    alpha: int,
) -> None:
    """Add a large, blurred color field that behaves like colored atmosphere."""

    mask = radial_mask(canvas.size, center, radius, strength=alpha, exponent=1.35)
    glow = Image.new("RGB", canvas.size, color)
    canvas.paste(glow, (0, 0), mask)


def vignette(canvas: Image.Image, *, strength: int = 150) -> None:
    """Deepen the outside edges while leaving the center legible."""

    width, height = canvas.size
    center_mask = radial_mask(
        canvas.size,
        (width / 2, height / 2),
        (width * 0.72, height * 0.78),
        strength=255,
        exponent=0.72,
    )
    edge_mask = ImageChops.invert(center_mask).point(lambda value: round(value * strength / 255))
    color_overlay(canvas, INK, edge_mask)


def smooth_noise(size: tuple[int, int], seed: int) -> Image.Image:
    """Return low-frequency monochrome texture for an atmosphere, not a flat blob."""

    # Image.effect_noise is deterministic, so artwork stays reproducible while
    # the enlarged and blurred texture gives glows a little visual grain.
    noise = Image.effect_noise((240, 135), 46 + (seed % 11))
    noise = noise.filter(ImageFilter.GaussianBlur(9)).resize(size, Image.Resampling.BICUBIC)
    return ImageOps.autocontrast(noise, cutoff=8)


def add_atmospheric_texture(
    canvas: Image.Image,
    color: tuple[int, int, int],
    *,
    alpha: int,
    seed: int,
    region: Image.Image | None = None,
) -> None:
    """Tint a restrained, soft noise field into the surrounding atmosphere."""

    mask = smooth_noise(canvas.size, seed).point(lambda value: round(value * alpha / 255))
    if region is not None:
        mask = ImageChops.multiply(mask, region)
    canvas.paste(color, (0, 0, canvas.width, canvas.height), mask)


def line_details(
    canvas: Image.Image,
    *,
    lines: list[tuple[list[tuple[int, int]], tuple[int, int, int, int], int]],
    nodes: list[tuple[tuple[int, int], tuple[int, int, int, int], int]] | None = None,
) -> None:
    """Draw hairline interface geometry with a restrained blurred underglow."""

    sharp = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    glow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    sharp_draw = ImageDraw.Draw(sharp)
    glow_draw = ImageDraw.Draw(glow)
    for points, color, width in lines:
        sharp_draw.line(points, fill=color, width=width, joint="curve")
        glow_draw.line(points, fill=(*color[:3], min(80, color[3])), width=max(3, width * 4), joint="curve")
    if nodes:
        for (x, y), color, radius in nodes:
            sharp_draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)
            glow_draw.ellipse(
                (x - radius * 3, y - radius * 3, x + radius * 3, y + radius * 3),
                fill=(*color[:3], min(70, color[3])),
            )
    glow = glow.filter(ImageFilter.GaussianBlur(8))
    canvas.paste(Image.alpha_composite(canvas.convert("RGBA"), glow).convert("RGB"))
    canvas.paste(Image.alpha_composite(canvas.convert("RGBA"), sharp).convert("RGB"))


def hero_artwork(red_source: Image.Image, blue_source: Image.Image) -> Image.Image:
    """Create the opening composition: negative space on the left, faces right."""

    canvas = Image.new("RGB", (WIDTH, HEIGHT), INK)
    soft_glow(canvas, (1430, 500), (740, 690), (55, 26, 42), alpha=92)
    soft_glow(canvas, (1720, 530), (520, 640), (18, 57, 76), alpha=76)

    # These overlapping photographs carry the detail.  Their local edge fades
    # are intentionally long so the smoke merges rather than looking collaged.
    # Keep the red subject to the inner-right and reserve the far-right for
    # the blue subject.  The blue layer is last, but its long left fade keeps
    # it from veiling the red face.
    paste_reference(
        canvas,
        red_source,
        (610, 125),
        1380,
        opacity=0.95,
        left=170,
        right=90,
        top=45,
        bottom=120,
        contrast=1.06,
        brightness=0.94,
    )
    paste_reference(
        canvas,
        blue_source,
        (1230, 230),
        1050,
        opacity=0.88,
        left=240,
        right=80,
        top=60,
        bottom=110,
        contrast=1.04,
        brightness=0.86,
    )

    # Keep the left 52% usable for slide copy without a hard rectangular seam.
    left_shadow = horizontal_mask(
        canvas.size,
        ((0, 238), (470, 232), (830, 182), (1070, 55), (1210, 0)),
        power=1.0,
    )
    color_overlay(canvas, INK, left_shadow)
    vignette(canvas, strength=112)
    add_atmospheric_texture(canvas, (28, 55, 65), alpha=22, seed=7, region=radial_mask(canvas.size, (1510, 490), (800, 700), strength=255))

    details = [
        ([(1160, 156), (1160, 390), (1195, 425)], (*CYAN, 74), 2),
        ([(1160, 156), (1372, 156)], (*CYAN, 74), 2),
        ([(1278, 870), (1390, 758), (1390, 645)], (*RED, 58), 2),
        ([(1390, 645), (1530, 505), (1808, 505)], (*RED, 58), 2),
        ([(1500, 925), (1500, 820), (1685, 635)], (*BLUE, 64), 2),
        ([(1685, 635), (1840, 635), (1900, 575)], (*BLUE, 64), 2),
        ([(1558, 191), (1810, 191), (1866, 247)], (205, 227, 235, 40), 1),
        ([(1810, 191), (1810, 312)], (205, 227, 235, 40), 1),
    ]
    nodes = [
        ((1160, 156), (*CYAN, 120), 3),
        ((1390, 645), (*RED, 110), 3),
        ((1500, 820), (*BLUE, 105), 3),
    ]
    line_details(canvas, lines=details, nodes=nodes)
    return canvas


def arena_artwork(red_source: Image.Image, blue_source: Image.Image) -> Image.Image:
    """Create a two-sided arena with an intentionally quiet diagram well."""

    canvas = Image.new("RGB", (WIDTH, HEIGHT), INK)
    soft_glow(canvas, (340, 420), (570, 660), (68, 18, 34), alpha=84)
    soft_glow(canvas, (1580, 420), (570, 660), (16, 52, 81), alpha=82)

    paste_reference(
        canvas,
        red_source,
        (-275, 40),
        1320,
        opacity=0.94,
        left=80,
        right=310,
        top=35,
        bottom=80,
        contrast=1.05,
        brightness=0.88,
    )
    paste_reference(
        canvas,
        blue_source,
        (875, 42),
        1320,
        opacity=0.92,
        left=310,
        right=80,
        top=35,
        bottom=80,
        contrast=1.05,
        brightness=0.87,
    )

    # A broad center veil keeps the area between the faces available for a
    # diagram while retaining the photographic smoke at its boundaries.
    center_shadow = horizontal_mask(
        canvas.size,
        ((0, 0), (490, 16), (700, 92), (960, 143), (1190, 92), (1430, 16), (1920, 0)),
    )
    color_overlay(canvas, INK, center_shadow)

    # The lower third is a dark foundation for annotations or a footer when
    # this background is placed into a deck.
    bottom_shadow = vertical_mask(
        canvas.size,
        ((0, 0), (625, 8), (715, 100), (820, 190), (1080, 222)),
    )
    color_overlay(canvas, INK, bottom_shadow)
    vignette(canvas, strength=120)
    add_atmospheric_texture(canvas, (23, 45, 61), alpha=17, seed=23, region=radial_mask(canvas.size, (960, 390), (920, 690), strength=255))

    details = [
        ([(642, 278), (642, 228), (692, 228)], (175, 216, 220, 42), 1),
        ([(1278, 278), (1278, 228), (1228, 228)], (175, 216, 220, 42), 1),
        ([(642, 578), (642, 628), (692, 628)], (175, 216, 220, 30), 1),
        ([(1278, 578), (1278, 628), (1228, 628)], (175, 216, 220, 30), 1),
        ([(736, 350), (1184, 350)], (100, 244, 208, 28), 1),
        ([(790, 515), (1130, 515)], (87, 158, 255, 24), 1),
    ]
    line_details(canvas, lines=details)
    return canvas


def quiet_artwork() -> Image.Image:
    """Create a mostly dark, face-free holding background."""

    canvas = Image.new("RGB", (WIDTH, HEIGHT), INK)
    # Layered fields and texture keep this restrained background atmospheric,
    # with no photographic subject competing with slide content.
    soft_glow(canvas, (250, 610), (700, 540), (21, 78, 73), alpha=50)
    soft_glow(canvas, (1710, 370), (610, 560), (84, 22, 42), alpha=38)
    soft_glow(canvas, (1080, 690), (820, 410), (12, 32, 48), alpha=26)
    texture_region = radial_mask(canvas.size, (980, 530), (1100, 720), strength=255, exponent=0.85)
    add_atmospheric_texture(canvas, (24, 81, 79), alpha=25, seed=41, region=texture_region)
    add_atmospheric_texture(canvas, (92, 28, 46), alpha=16, seed=43, region=radial_mask(canvas.size, (1590, 370), (650, 570), strength=255))

    grid = []
    for x in range(120, WIDTH + 1, 160):
        grid.append(([(x, 150), (x, 925)], (100, 244, 208, 18), 1))
    for y in range(165, 926, 128):
        grid.append(([(115, y), (1805, y)], (100, 244, 208, 15), 1))
    # A few broken red/cyan traces give the grid a designed edge without
    # turning it into a dense sci-fi pattern.
    grid.extend(
        [
            ([(143, 790), (345, 790), (420, 715), (590, 715)], (*RED, 46), 1),
            ([(1330, 250), (1510, 250), (1590, 330), (1790, 330)], (*CYAN, 44), 1),
            ([(1570, 795), (1660, 705), (1800, 705)], (*RED, 34), 1),
            ([(1325, 835), (1428, 835), (1480, 783)], (*BLUE, 33), 1),
        ]
    )
    line_details(canvas, lines=grid)
    vignette(canvas, strength=132)
    return canvas


def save_jpeg(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(path, format="JPEG", quality=94, subsampling=0, optimize=True)


def generate(output_dir: Path) -> list[Path]:
    """Generate all requested assets and return their exact paths."""

    red_source = Image.open(RED_REFERENCE).convert("RGB")
    blue_source = Image.open(BLUE_REFERENCE).convert("RGB")
    outputs = {
        "hero.jpg": hero_artwork(red_source, blue_source),
        "arena.jpg": arena_artwork(red_source, blue_source),
        "quiet.jpg": quiet_artwork(),
    }
    paths = []
    for filename, image in outputs.items():
        path = output_dir / filename
        save_jpeg(image, path)
        paths.append(path)
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "assets",
        help="directory for generated JPEG assets (default: presentation/assets)",
    )
    args = parser.parse_args()
    if not RED_REFERENCE.exists() or not BLUE_REFERENCE.exists():
        raise FileNotFoundError("Expected mask reference images in src/bayora/static")
    for path in generate(args.output_dir):
        with Image.open(path) as image:
            print(f"{path} {image.width}x{image.height}")


if __name__ == "__main__":
    main()
