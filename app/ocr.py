"""OCR: turn an image of a document into text.

OCR = Optical Character Recognition. The engine (Tesseract, open source,
originally from HP/Google) looks at the pixels, finds letter shapes, and
outputs characters — plus a confidence score for how sure it is.

Real documents are photographed at angles, in bad light, slightly blurry.
So before recognizing, we PREPROCESS the image to make the engine's job
easier. More preprocessing steps get added here as we meet messier bills.
"""

from pathlib import Path

import pytesseract
from PIL import Image, ImageOps


def preprocess(image: Image.Image) -> Image.Image:
    """Clean the image up before recognition.

    Step 1: grayscale — color carries no meaning for text shapes,
            and removing it reduces noise.
    Step 2: autocontrast — stretch brightness so faint text darkens
            and the background whitens.
    (Later: deskewing tilted photos, removing shadows, upscaling.)
    """
    gray = ImageOps.grayscale(image)
    return ImageOps.autocontrast(gray)


def extract_text(file_path: str | Path) -> dict:
    """Run OCR on an image file and return text + confidence.

    Returns: {"text": str, "confidence": float 0-100, "word_count": int}
    """
    image = Image.open(file_path)
    cleaned = preprocess(image)

    # The recognized text itself.
    text = pytesseract.image_to_string(cleaned)

    # Word-level confidences (how sure the engine is about each word).
    # -1 marks non-word boxes; we average only the real words.
    data = pytesseract.image_to_data(cleaned, output_type=pytesseract.Output.DICT)
    confidences = [int(c) for c in data["conf"] if int(c) >= 0]
    avg_confidence = round(sum(confidences) / len(confidences), 1) if confidences else 0.0

    return {
        "text": text.strip(),
        "confidence": avg_confidence,
        "word_count": len(text.split()),
    }
