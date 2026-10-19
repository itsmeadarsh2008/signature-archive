#!/usr/bin/env python3
"""Add signature images to assets/ as transparent PNGs with white ink.

Run it with no arguments for an endless prompt (blank URL or Ctrl-C stops),
or add a single signature straight from the command line:

    python3 fill.py https://example.com/sign.png "Pablo Picasso"

By default the saved file is assets/<artist name>.png. The artist name is used
exactly as typed; its background is fully transparent and all ink is pure
white, regardless of the source colours.

Pass --raw to skip that processing and keep the downloaded file untouched
(useful when the source is already prepared). Raw files keep their original
extension.

Requires Pillow. SVG input additionally needs rsvg-convert (librsvg) or
ImageMagick.
"""

from __future__ import annotations

import argparse
import io
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ElementTree
from pathlib import Path

try:
    from PIL import Image, ImageChops, ImageOps
except ImportError:  # pragma: no cover - friendly error for a missing dependency
    sys.exit("fill.py needs Pillow: python3 -m pip install Pillow")


ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
MAX_DOWNLOAD = 50 * 1024 * 1024  # 50 MB
SVG_WIDTH = 2048
PREVIEW_WIDTH = "50"
USER_AGENT = "signature-archive-fill/1.0"

EXTENSION_BY_MIME = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/pjpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/svg+xml": ".svg",
    "image/avif": ".avif",
    "image/bmp": ".bmp",
    "image/x-ms-bmp": ".bmp",
    "image/tiff": ".tiff",
    "image/heic": ".heic",
    "image/heif": ".heif",
    "image/jxl": ".jxl",
    "image/x-icon": ".ico",
    "image/vnd.microsoft.icon": ".ico",
}

EXTENSION_BY_FORMAT = {
    "PNG": ".png",
    "JPEG": ".jpg",
    "MPO": ".jpg",
    "WEBP": ".webp",
    "GIF": ".gif",
    "BMP": ".bmp",
    "TIFF": ".tiff",
    "AVIF": ".avif",
    "ICO": ".ico",
    "JXL": ".jxl",
    "HEIC": ".heic",
    "HEIF": ".heif",
}

CANONICAL_EXTENSIONS = {
    ".jpeg": ".jpg",
    ".jpe": ".jpg",
    ".jfif": ".jpg",
    ".tif": ".tiff",
}

IMAGE_EXTENSIONS = (
    set(EXTENSION_BY_MIME.values())
    | set(EXTENSION_BY_FORMAT.values())
    | set(CANONICAL_EXTENSIONS)
    | {".svg"}
)


class FillError(Exception):
    """A recoverable problem while adding a signature."""


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def validate_artist_name(name: str) -> str:
    """Return the artist name unchanged, or reject names that cannot be files.

    The on-disk name is exactly what was typed: case, spaces, punctuation and
    Unicode are preserved. Path separators and control characters are refused
    rather than silently rewritten.
    """
    if not name.strip():
        raise FillError("artist name is required")
    if name in {".", ".."}:
        raise FillError("artist name cannot be '.' or '..'")
    if "/" in name or "\\" in name:
        raise FillError("artist name cannot contain path separators")
    if "\x00" in name:
        raise FillError("artist name cannot contain NUL bytes")
    if any(ord(character) < 32 for character in name):
        raise FillError("artist name cannot contain control characters")
    return name


def download(url: str) -> tuple[bytes, str]:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise FillError("URL must start with http:// or https://")

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "image/*,*/*;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read(MAX_DOWNLOAD + 1)
            content_type = response.headers.get("Content-Type", "")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise FillError(f"could not download image: {exc}") from exc

    if len(data) > MAX_DOWNLOAD:
        raise FillError("image is larger than 50 MB")
    if not data:
        raise FillError("downloaded file is empty")
    return data, content_type


def is_svg(data: bytes, content_type: str, url: str) -> bool:
    mime = (content_type or "").split(";", 1)[0].strip().lower()
    if mime == "image/svg+xml":
        return True
    if urllib.parse.urlparse(url).path.lower().endswith(".svg"):
        return True
    head = data[:2048].lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    return b"<svg" in head


def open_with_pillow(data: bytes) -> Image.Image:
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
        return image
    except Exception as exc:
        raise FillError(f"downloaded file is not a readable image ({exc})") from exc


def run_converter(command: list[str], data: bytes, name: str) -> Image.Image:
    try:
        result = subprocess.run(
            command,
            input=data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise FillError(f"{name} failed: {exc}") from exc

    if result.returncode != 0 or not result.stdout:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise FillError(
            f"{name} could not render the image{': ' + detail if detail else ''}"
        )
    return open_with_pillow(result.stdout)


def rasterize_svg(data: bytes) -> Image.Image:
    if shutil.which("rsvg-convert"):
        return run_converter(
            [
                "rsvg-convert",
                "--format=png",
                f"--width={SVG_WIDTH}",
                "--keep-aspect-ratio",
            ],
            data,
            "rsvg-convert",
        )

    if shutil.which("magick"):
        return run_converter(
            ["magick", "-background", "none", "svg:-", "png:-"],
            data,
            "ImageMagick",
        )

    raise FillError("SVG input needs rsvg-convert (librsvg) or ImageMagick installed")


def load_raster(data: bytes) -> Image.Image:
    try:
        return open_with_pillow(data)
    except FillError as pillow_error:
        if not shutil.which("magick"):
            raise pillow_error
        # ImageMagick can decode formats Pillow does not support (AVIF, HEIC, ...).
        try:
            return run_converter(["magick", "-", "png:-"], data, "ImageMagick")
        except FillError:
            raise pillow_error


def validate_svg(data: bytes) -> None:
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError as exc:
        raise FillError(f"downloaded SVG is invalid ({exc})") from exc
    tag = root.tag.rsplit("}", 1)[-1].lower()
    if tag != "svg":
        raise FillError("downloaded file is not an SVG image")


def image_extension(data: bytes, content_type: str, url: str) -> str:
    """Pick the extension for a raw (unprocessed) download."""
    if is_svg(data, content_type, url):
        return ".svg"

    try:
        with Image.open(io.BytesIO(data)) as image:
            image_format = (image.format or "").upper()
    except Exception:
        image_format = ""
    if image_format in EXTENSION_BY_FORMAT:
        return EXTENSION_BY_FORMAT[image_format]

    mime = (content_type or "").split(";", 1)[0].strip().lower()
    if mime in EXTENSION_BY_MIME:
        return EXTENSION_BY_MIME[mime]

    suffix = Path(urllib.parse.urlparse(url).path).suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        return CANONICAL_EXTENSIONS.get(suffix, suffix)

    raise FillError("could not determine the image file format")


def write_asset(
    artist: str,
    extension: str,
    *,
    data: bytes | None = None,
    image: Image.Image | None = None,
) -> tuple[Path, bool]:
    """Atomically write one asset and remove other formats for the same name."""
    ASSETS.mkdir(parents=True, exist_ok=True)
    filename = f"{artist}{extension}"
    if len(os.fsencode(filename)) > 255:
        raise FillError("artist name is too long for a filename")

    path = ASSETS / filename
    existed = path.exists()
    temporary = path.with_name(f".{path.name}.tmp")

    try:
        if image is not None:
            image.save(temporary, format="PNG", optimize=True)
        else:
            temporary.write_bytes(data or b"")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()

    # One artist name should resolve to exactly one file, even when switching
    # between processed PNGs and raw originals.
    for candidate in ASSETS.iterdir():
        if not candidate.is_file() or candidate == path:
            continue
        suffix = candidate.suffix
        if suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        if candidate.name != f"{artist}{suffix}":
            continue
        try:
            candidate.unlink()
            print(f"Removed previous {display_path(candidate)}")
        except OSError as exc:
            print(
                f"Warning: could not remove {display_path(candidate)}: {exc}",
                file=sys.stderr,
            )

    return path, existed


def median(values: list[int]) -> int:
    if not values:
        return 0
    values.sort()
    return values[len(values) // 2]


def border_values(channel: Image.Image) -> list[int]:
    """Sample pixels around the edge of a single-channel image."""
    width, height = channel.size
    pixels = channel.load()
    values: list[int] = []
    step_x = max(1, width // 256)
    step_y = max(1, height // 256)

    for x in range(0, width, step_x):
        values.append(pixels[x, 0])
        values.append(pixels[x, height - 1])
    for y in range(0, height, step_y):
        values.append(pixels[0, y])
        values.append(pixels[width - 1, y])
    return values


def median_luma(image: Image.Image) -> int:
    thumb = image.copy()
    thumb.thumbnail((256, 256))
    histogram = thumb.convert("L").histogram()
    midpoint = sum(histogram) / 2
    seen = 0
    for value, count in enumerate(histogram):
        seen += count
        if seen >= midpoint:
            return value
    return 255


def has_cutout_background(rgba: Image.Image) -> bool:
    """True when the source already has a genuinely transparent background.

    A transparent margin around an opaque scan does not count: the area
    inside the alpha bounding box is still opaque in that case.
    """
    alpha = rgba.getchannel("A")
    if alpha.getextrema()[0] == 255:
        return False

    box = alpha.getbbox()
    if box is None:
        raise FillError("image is completely transparent")

    inner = alpha.crop(box)
    transparent = sum(inner.histogram()[:128])
    return transparent / (inner.width * inner.height) > 0.01


def ink_mask_from_opaque(rgb: Image.Image) -> Image.Image:
    """Build an alpha mask from ink on a plain light or dark background."""
    red, green, blue = rgb.split()
    darker = ImageChops.lighter(
        ImageChops.lighter(ImageOps.invert(red), ImageOps.invert(green)),
        ImageOps.invert(blue),
    )
    lighter = ImageChops.lighter(ImageChops.lighter(red, green), blue)

    # Light paper with dark ink is the common case; the inverse handles
    # white signatures saved on a dark background.
    mask = darker if median_luma(rgb) >= 128 else lighter

    # Remove the residual tone of the background (off-white paper, JPEG
    # noise, dark-grey backdrops), then stretch what is left so the core of
    # the ink reaches fully opaque white.
    background = min(64, median(border_values(mask)))
    if background:
        mask = ImageChops.subtract(mask, Image.new("L", mask.size, background))
    mask = mask.point(lambda value: 0 if value < 8 else value)

    # Stretch the ink so its strongest point is fully opaque white.
    highest = mask.getextrema()[1]
    if highest:
        gain = 255 / highest
        mask = mask.point(lambda value: min(255, round(value * gain)))
    return mask


def to_white_ink(image: Image.Image) -> Image.Image:
    try:
        image.seek(0)
    except (AttributeError, EOFError):
        pass

    image = ImageOps.exif_transpose(image)
    rgba = image.convert("RGBA")

    if has_cutout_background(rgba):
        mask = rgba.getchannel("A")
    else:
        flat = Image.alpha_composite(
            Image.new("RGBA", rgba.size, (255, 255, 255, 255)), rgba
        ).convert("RGB")
        mask = ink_mask_from_opaque(flat)

    if mask.getextrema()[1] == 0:
        raise FillError("no ink found in the image")

    result = Image.new("RGBA", rgba.size, (255, 255, 255, 0))
    result.putalpha(mask)
    return result


def add_signature(
    url: str,
    artist: str,
    *,
    process: bool = True,
    preview: bool = True,
) -> Path:
    artist = validate_artist_name(artist)

    print(f"Downloading {url} ...")
    data, content_type = download(url)
    svg = is_svg(data, content_type, url)

    if process:
        source = rasterize_svg(data) if svg else load_raster(data)
        result = to_white_ink(source)
        path, existed = write_asset(artist, ".png", image=result)
        width, height = result.size
        detail = f"{width}x{height}, transparent background, white ink"
    else:
        if svg:
            validate_svg(data)
        else:
            load_raster(data)  # validate the download without modifying it
        extension = image_extension(data, content_type, url)
        path, existed = write_asset(artist, extension, data=data)
        detail = f"{len(data):,} bytes, original file"

    action = "Updated" if existed else "Added"
    print(f"{action} {display_path(path)} ({detail})")
    if preview:
        preview_image(path)
    return path


def preview_png(path: Path) -> bytes | None:
    """Return a PNG version of the saved asset for terminal preview."""
    try:
        data = path.read_bytes()
        if path.suffix.lower() == ".png":
            return data

        image = (
            rasterize_svg(data) if is_svg(data, "", str(path)) else load_raster(data)
        )
        buffer = io.BytesIO()
        image.save(buffer, format="PNG", optimize=True)
        return buffer.getvalue()
    except (OSError, FillError):
        return None


def in_wezterm() -> bool:
    return bool(
        os.environ.get("WEZTERM_PANE")
        or os.environ.get("WEZTERM_EXECUTABLE")
        or os.environ.get("TERM_PROGRAM") == "WezTerm"
    )


def preview_image(path: Path) -> None:
    """Show a PNG preview of the saved asset when running inside WezTerm.

    The PNG copy is only for the inline preview. The file in assets/ is never
    converted or modified, and this path does nothing outside WezTerm.
    """
    if not sys.stdout.isatty():
        return
    if not in_wezterm():
        return

    wezterm = shutil.which("wezterm")
    if not wezterm:
        return

    png = preview_png(path)
    if png is None:
        return

    sys.stdout.flush()
    try:
        subprocess.run(
            [wezterm, "imgcat", "--width", PREVIEW_WIDTH],
            input=png,
            check=False,
            stderr=subprocess.DEVNULL,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def prompt(label: str, *, strip: bool = True) -> str:
    try:
        value = input(label)
    except EOFError:
        return ""
    return value.strip() if strip else value


def choose_mode(default_process: bool) -> bool:
    if not sys.stdin.isatty():
        return default_process

    default = "w" if default_process else "r"
    answer = prompt(
        f"Processing mode: [w]hite ink / [r]aw original [{default}]: "
    ).lower()
    if not answer:
        return default_process
    return answer not in {"r", "raw", "n", "no"}


def endless_form(
    default_process: bool = True,
    preview: bool = True,
) -> int:
    print("Signature Archive - endless fill form")
    print("Leave the URL blank or press Ctrl-C to stop.\n")

    process = choose_mode(default_process)
    print(f"Mode: {'white ink' if process else 'raw original'}\n")

    while True:
        try:
            url = prompt("Image URL: ")
            if not url:
                break

            artist = prompt("Artist name: ", strip=False)
            if not artist.strip():
                print("Artist name is required, skipping this one.\n")
                continue

            try:
                add_signature(url, artist, process=process, preview=preview)
            except FillError as exc:
                print(f"Error: {exc}", file=sys.stderr)
            print()
        except (KeyboardInterrupt, EOFError):
            break

    print("Done.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Add a signature to assets/ with a transparent background and "
            "white ink. With no arguments, keeps prompting for more."
        )
    )
    parser.add_argument("url", nargs="?", help="image URL")
    parser.add_argument(
        "artist", nargs="*", help='artist name, for example "Pablo Picasso"'
    )
    parser.add_argument(
        "--raw",
        "--no-process",
        dest="raw",
        action="store_true",
        help="keep the downloaded file untouched instead of converting it",
    )
    parser.add_argument(
        "--no-preview",
        dest="preview",
        action="store_false",
        help="do not show the saved image with wezterm imgcat",
    )
    parser.add_argument(
        "--key",
        metavar="ARTIST",
        help="print the exact asset name for an artist and exit",
    )
    args = parser.parse_args(argv)

    if args.key is not None:
        try:
            key = validate_artist_name(args.key)
        except FillError as exc:
            parser.error(str(exc))
        print(key)
        return 0

    if args.url:
        artist = " ".join(args.artist)
        if not artist.strip():
            parser.error("an artist name is required when a URL is given")
        try:
            add_signature(
                args.url,
                artist,
                process=not args.raw,
                preview=args.preview,
            )
        except FillError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        return 0

    if args.artist:
        parser.error("a URL is required when an artist name is given")

    return endless_form(
        default_process=not args.raw,
        preview=args.preview,
    )


if __name__ == "__main__":
    raise SystemExit(main())
