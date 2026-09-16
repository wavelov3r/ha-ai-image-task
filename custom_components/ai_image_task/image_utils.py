"""Optional post-processing: bring the generated image to the exact size.

Providers often have minimum/step constraints on the requested dimensions
(``zimage`` refuses anything below 512px per side), so the picture that comes
back may be larger than what an e-ink panel expects.  These helpers resize it
to the exact target.

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

_PIL_WARNED = False


def pillow_available() -> bool:
    """Whether Pillow can be imported."""
    try:
        import PIL  # noqa: F401
    except ImportError:
        return False
    return True


def fit_image(
    data: bytes,
    width: int,
    height: int,
    fit: str = FIT_COVER,
    pad_color: str = "#ffffff",
    jpeg_quality: int = 92,
) -> tuple[bytes, str]:
    """Resize ``data`` to exactly ``width`` x ``height``.

    ``cover`` crops the overflowing side (no distortion, fills the frame),
    ``contain`` letterboxes with ``pad_color``, ``stretch`` distorts.
    Returns the new bytes and their content type; on any failure the input is
    returned unchanged.
    """
    global _PIL_WARNED  # noqa: PLW0603

    try:
        from PIL import Image, ImageOps
    except ImportError:
        if not _PIL_WARNED:
            _LOGGER.warning(
                "Pillow is not installed: images are saved at the size returned "
                "by the provider instead of the exact configured size"
            )
            _PIL_WARNED = True
        return data, ""

    width = max(int(width), 1)
    height = max(int(height), 1)

    try:
        with Image.open(BytesIO(data)) as img:
            img.load()
            if img.size == (width, height):
                return data, ""

            has_alpha = img.mode in ("RGBA", "LA", "P") and "transparency" in img.info
            if fit == FIT_STRETCH:
                out = img.convert("RGBA" if has_alpha else "RGB").resize(
                    (width, height), Image.LANCZOS
                )
            elif fit == FIT_CONTAIN:
                out = ImageOps.pad(
                    img.convert("RGBA" if has_alpha else "RGB"),
                    (width, height),
                    method=Image.LANCZOS,
                    color=None if has_alpha else pad_color,
                    centering=(0.5, 0.5),
                )
            else:
                out = ImageOps.fit(
                    img.convert("RGBA" if has_alpha else "RGB"),
                    (width, height),
                    method=Image.LANCZOS,
                    centering=(0.5, 0.5),
                )

            buffer = BytesIO()
            if has_alpha:
                out.save(buffer, format="PNG", optimize=True)
                content_type = "image/png"
            else:
                out.save(
                    buffer, format="JPEG", quality=jpeg_quality, optimize=True
                )
                content_type = "image/jpeg"
            return buffer.getvalue(), content_type
    except Exception as err:  # noqa: BLE001 - never lose the image over this
        _LOGGER.warning("Cannot resize the generated image (%s); keeping it as is", err)
        return data, ""
