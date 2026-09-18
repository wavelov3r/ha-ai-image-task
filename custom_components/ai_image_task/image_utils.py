"""Post-processing: exact size, real file format and colour depth.

Two things make this module necessary:

* Providers have minimum/step constraints on the requested size (``zimage``
  refuses anything below 512px per side), so the picture that comes back is
  usually bigger than what an e-ink panel expects.
* Pollinations always answers with **JPEG** bytes, whatever extension you give
  the file.  ESPHome's ``online_image`` checks the real signature, so a JPEG
  named ``.png`` fails with "incorrect PNG signature".  Here the bytes are
  actually re-encoded.

Pillow is an optional dependency: when it is missing the original bytes are
returned untouched and a warning is logged once.
"""

from __future__ import annotations

import logging
from io import BytesIO

_LOGGER = logging.getLogger(__name__)

FIT_COVER = "cover"
FIT_CONTAIN = "contain"
FIT_STRETCH = "stretch"
FIT_MODES = [FIT_COVER, FIT_CONTAIN, FIT_STRETCH]

FORMAT_AUTO = "auto"
FORMAT_PNG = "png"
FORMAT_JPEG = "jpeg"
FORMAT_KEEP = "keep"
OUTPUT_FORMATS = [FORMAT_AUTO, FORMAT_PNG, FORMAT_JPEG, FORMAT_KEEP]

COLOR_RGB = "color"
COLOR_GRAYSCALE = "grayscale"
COLOR_BW = "bw"
COLOR_MODES = [COLOR_RGB, COLOR_GRAYSCALE, COLOR_BW]

MIN_BW_LEVELS = 2
MAX_BW_LEVELS = 8
DEFAULT_BW_LEVELS = 2

_CONTENT_TYPES = {"png": "image/png", "jpeg": "image/jpeg"}
_EXTENSIONS = {"png": ".png", "jpeg": ".jpg"}

_PIL_WARNED = False


def _dither_to_levels(img, levels: int):
    """Error-diffusion (Floyd-Steinberg) quantisation to ``levels`` evenly
    spaced gray shades.

    ``Image.convert("1")`` only ever produces 2 levels; e-ink panels with a
    real gray scale (3/4/16 levels) look banded/streaky if the 256-shade
    grayscale image is sent as-is and thresholded on the device instead.
    Building an explicit palette with exactly ``levels`` evenly spaced grays
    and letting Pillow dither onto it keeps the classic Floyd-Steinberg error
    diffusion while matching the panel's real capabilities.
    """
    from PIL import Image

    levels = max(MIN_BW_LEVELS, min(int(levels), MAX_BW_LEVELS))
    shades = [round(i * 255 / (levels - 1)) for i in range(levels)]

    palette_img = Image.new("P", (1, 1))
    palette = []
    for shade in shades:
        palette.extend([shade, shade, shade])
    palette.extend([0, 0, 0] * (256 - len(shades)))
    palette_img.putpalette(palette)

    quantized = img.convert("L").convert("RGB").quantize(
        palette=palette_img, dither=Image.Dither.FLOYDSTEINBERG
    )
    return quantized.convert("L")


def pillow_available() -> bool:
    """Whether Pillow can be imported."""
    try:
        import PIL  # noqa: F401
    except ImportError:
        return False
    return True


def detect_format(data: bytes) -> str | None:
    """Real format of ``data`` based on its magic bytes."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    return None


def format_from_filename(filename: str) -> str | None:
    """Format implied by a file extension, or ``None`` when unknown."""
    ext = (filename or "").rsplit(".", 1)[-1].lower()
    if ext == "png":
        return "png"
    if ext in ("jpg", "jpeg"):
        return "jpeg"
    return None


def extension_for(fmt: str) -> str:
    """Canonical extension of a format."""
    return _EXTENSIONS.get(fmt, ".jpg")


def content_type_for(fmt: str) -> str:
    """Content type of a format."""
    return _CONTENT_TYPES.get(fmt, "image/jpeg")


def resolve_target_format(
    output_format: str, filename: str, data: bytes
) -> str | None:
    """Which format the saved file should be in.

    ``auto`` follows the file extension (this is what makes a ``.png`` file
    really contain PNG), ``keep`` leaves the provider bytes alone, and the
    explicit values win over everything.  ``None`` means "no conversion".
    """
    if output_format == FORMAT_KEEP:
        return None
    if output_format in (FORMAT_PNG, FORMAT_JPEG):
        return output_format
    return format_from_filename(filename) or detect_format(data)


def process_image(
    data: bytes,
    width: int,
    height: int,
    fit: str = FIT_COVER,
    exact_size: bool = True,
    target_format: str | None = None,
    color_mode: str = COLOR_RGB,
    pad_color: str = "#ffffff",
    jpeg_quality: int = 92,
    bw_levels: int = DEFAULT_BW_LEVELS,
) -> tuple[bytes, str]:
    """Resize and/or re-encode ``data``.

    Returns the processed bytes and their content type.  The original bytes
    and an empty content type are returned when nothing had to change or when
    Pillow is unavailable.
    """
    global _PIL_WARNED  # noqa: PLW0603

    current_format = detect_format(data)
    needs_format = target_format is not None and target_format != current_format
    needs_color = color_mode != COLOR_RGB

    if not (exact_size or needs_format or needs_color):
        return data, ""

    try:
        from PIL import Image, ImageOps
    except ImportError:
        if not _PIL_WARNED:
            _LOGGER.warning(
                "Pillow is not installed: images are saved exactly as the "
                "provider returned them (no resize, no format conversion)"
            )
            _PIL_WARNED = True
        return data, ""

    width = max(int(width), 1)
    height = max(int(height), 1)
    fmt = target_format or current_format or "jpeg"
    if fmt not in ("png", "jpeg"):
        fmt = "png"

    try:
        with Image.open(BytesIO(data)) as img:
            img.load()
            needs_resize = exact_size and img.size != (width, height)

            if not (needs_resize or needs_format or needs_color):
                return data, ""

            keep_alpha = fmt == "png" and (
                img.mode in ("RGBA", "LA")
                or (img.mode == "P" and "transparency" in img.info)
            )
            base_mode = "RGBA" if keep_alpha else "RGB"
            out = img.convert(base_mode)

            if needs_resize:
                if fit == FIT_STRETCH:
                    out = out.resize((width, height), Image.LANCZOS)
                elif fit == FIT_CONTAIN:
                    out = ImageOps.pad(
                        out,
                        (width, height),
                        method=Image.LANCZOS,
                        color=None if keep_alpha else pad_color,
                        centering=(0.5, 0.5),
                    )
                else:
                    out = ImageOps.fit(
                        out,
                        (width, height),
                        method=Image.LANCZOS,
                        centering=(0.5, 0.5),
                    )

            if color_mode == COLOR_GRAYSCALE:
                out = out.convert("L")
            elif color_mode == COLOR_BW:
                # Error-diffusion (Floyd-Steinberg) dithering to the panel's
                # real number of gray levels, done *after* the resize so the
                # dither pattern matches the final pixel grid (dithering
                # before resizing gets blurred/re-sampled by LANCZOS and
                # turns into visible streaks/banding on e-ink panels).
                out = _dither_to_levels(out, bw_levels)

            buffer = BytesIO()
            if fmt == "png":
                # Non-interlaced 8-bit PNG: what ESPHome's decoder expects.
                out.save(buffer, format="PNG", optimize=True, interlace=False)
            else:
                out.save(buffer, format="JPEG", quality=jpeg_quality, optimize=True)
            return buffer.getvalue(), content_type_for(fmt)
    except Exception as err:  # noqa: BLE001 - never lose the image over this
        _LOGGER.warning(
            "Cannot post-process the generated image (%s); keeping it as is", err
        )
        return data, ""


# Backwards-compatible alias used by earlier versions.
def fit_image(
    data: bytes, width: int, height: int, fit: str = FIT_COVER
) -> tuple[bytes, str]:
    """Resize only, keeping the original format."""
    return process_image(data, width, height, fit=fit, exact_size=True)
