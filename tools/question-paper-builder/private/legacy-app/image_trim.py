"""Right-edge whitespace trimming for cropped question images.

Only the right edge is changed. Left, top, and bottom coordinates stay intact.
"""

from PIL import Image

try:
    import numpy as np
except ImportError:  # Pillow-only fallback for a fresh maintenance machine.
    np = None


def _ink_data(image):
    rgb = image.convert("RGB")
    width, height = rgb.size
    if np is not None:
        pixels = np.asarray(rgb)
        ink = np.min(pixels, axis=2) < 248
        return ink.sum(axis=0).astype(int).tolist(), ink

    pixels = rgb.load()
    counts = [0] * width
    for x in range(width):
        counts[x] = sum(1 for y in range(height) if min(pixels[x, y]) < 248)
    return counts, rgb


def find_right_trim_width(image, margin=18):
    width, height = image.size
    if width < 100:
        return width

    counts, _ink_data_unused = _ink_data(image)

    # Every real mark counts, including dense borders, tables and diagrams.
    # The previous implementation ignored dense columns near the right edge;
    # that incorrectly removed parts of infographics and reading passages.
    content_columns = [x for x, count in enumerate(counts) if count >= 2]
    if not content_columns:
        return width

    last_content = content_columns[-1]
    minimum_width = int(width * 0.30)
    return min(width, max(minimum_width, last_content + 1 + margin))


def trim_right_whitespace(image, margin=18):
    new_width = find_right_trim_width(image, margin=margin)
    if new_width >= image.width:
        return image
    return image.crop((0, 0, new_width, image.height))