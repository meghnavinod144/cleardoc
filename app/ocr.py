"""OCR: turn an image of a document into text.

OCR = Optical Character Recognition. The engine (Tesseract, open source,
originally from HP/Google) looks at the pixels, finds letter shapes, and
outputs characters — plus a confidence score for how sure it is.

Real documents are photographed at angles, in bad light, slightly blurry.
So before recognizing, we PREPROCESS the image to make the engine's job
easier. More preprocessing steps get added here as we meet messier bills.
"""

import subprocess
from pathlib import Path

import pytesseract
from pdf2image import convert_from_path
from PIL import Image, ImageOps

# OCR a maximum of this many PDF pages (cost + time guard).
MAX_PDF_PAGES = 5


def preprocess(image: Image.Image) -> Image.Image:
    """Clean the image up before recognition.

    Step 1: grayscale — color carries no meaning for text shapes.
    Step 2: upscale small images — phone photos of far-away documents
            give Tesseract too few pixels per letter; 2x helps.
    Step 3: autocontrast — faint text darkens, background whitens.

    A median denoise filter was TRIED here and REMOVED: measurement on a
    degraded test photo showed it lowered confidence (91.8 vs 92.8) —
    it blurred letter edges more than it removed noise. Lesson kept in
    LEARNING.md: measure every preprocessing step, never assume it helps.
    """
    gray = ImageOps.grayscale(image)
    if gray.width < 800:
        gray = gray.resize((gray.width * 2, gray.height * 2), Image.LANCZOS)
    return ImageOps.autocontrast(gray)


def pdf_text_layer(file_path: Path) -> str:
    """Try reading a PDF's embedded text layer (no OCR needed).

    Two kinds of PDF exist:
      - BORN-DIGITAL (made by software, e.g. a bill downloaded from the
        electricity board's website): the real text is embedded inside —
        extract it directly, perfectly, for free.
      - SCANNED (a photo wrapped in a PDF): no text inside, just an
        image — must OCR.
    We try the free path first; if it yields almost nothing, it's a scan.
    """
    result = subprocess.run(
        ["pdftotext", "-layout", str(file_path), "-"],
        capture_output=True, text=True, timeout=30,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def extract_text(file_path: str | Path) -> dict:
    """Extract text from an image OR a PDF.

    Returns: {"text": str, "confidence": float 0-100, "word_count": int,
              "method": how the text was obtained}
    """
    file_path = Path(file_path)

    if file_path.suffix.lower() == ".pdf":
        # Free path: born-digital PDF with an embedded text layer.
        embedded = pdf_text_layer(file_path)
        if len(embedded.split()) >= 20:  # real content, not just noise
            return {
                "text": embedded,
                "confidence": 100.0,  # digital text is exact — no guessing
                "word_count": len(embedded.split()),
                "method": "pdf_text_layer",
            }
        # Scanned PDF: turn pages into images, OCR each, join the text.
        pages = convert_from_path(file_path, dpi=300, last_page=MAX_PDF_PAGES)
        results = [_ocr_image(page) for page in pages]
        all_text = "\n\n".join(r["text"] for r in results)
        min_conf = min((r["confidence"] for r in results), default=0.0)
        return {
            "text": all_text.strip(),
            "confidence": min_conf,  # honest: report the WORST page
            "word_count": len(all_text.split()),
            "method": f"ocr_scanned_pdf_{len(pages)}_pages",
        }

    result = _ocr_image(Image.open(file_path))
    result["method"] = "ocr_image"
    return result


def _ocr_image(image: Image.Image) -> dict:
    """OCR one image (shared by direct images and scanned PDF pages)."""
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
