"""Step 4: Stress-test the OCR. Degrade the scan on purpose and watch how it fails.

Run from the mandate-extractor folder with the venv active:
    python stress_ocr.py

For each degraded version of the scan it reports:
  - similarity to the real text layer
  - how many field values survived exactly (e.g. "NGN 500,000")
  - Tesseract's average word confidence, and its least confident words
"""
import difflib
import random
import shutil
from pathlib import Path

import pypdfium2 as pdfium
import pytesseract
from PIL import Image, ImageFilter
from pypdf import PdfReader

SAMPLES = Path("samples")
SCAN = SAMPLES / "mandate_001_scan.pdf"
TEXT = SAMPLES / "mandate_001_text.pdf"

DEFAULT_TESSERACT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if not shutil.which("tesseract") and Path(DEFAULT_TESSERACT).exists():
    pytesseract.pytesseract.tesseract_cmd = DEFAULT_TESSERACT


# ---------- loading ----------

def render(path, dpi):
    pdf = pdfium.PdfDocument(str(path))
    image = pdf[0].render(scale=dpi / 72).to_pil().convert("L")
    pdf.close()
    return image


def text_layer(path):
    return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)


def clean_lines(text):
    return [line.strip() for line in text.splitlines() if line.strip()]


def parse_fields(lines):
    """Turn 'Key: value' lines into a dict."""
    fields = {}
    for line in lines:
        if ": " in line:
            key, value = line.split(": ", 1)
            fields[key.strip()] = value.strip()
    return fields


# ---------- ways to damage a scan ----------

def low_res(_):
    return render(SCAN, dpi=100)


def blurred(img):
    return img.filter(ImageFilter.GaussianBlur(radius=2))


def speckled(img, amount=0.03, seed=42):
    """Salt-and-pepper noise, like dust on a scanner glass. Seeded so runs repeat."""
    img = img.copy()
    rng = random.Random(seed)
    w, h = img.size
    px = img.load()
    for _ in range(int(w * h * amount)):
        px[rng.randrange(w), rng.randrange(h)] = rng.choice((0, 255))
    return img


def tilted(img):
    return img.rotate(3, expand=True, fillcolor=255)


def everything(_):
    return tilted(speckled(blurred(render(SCAN, dpi=150))))


# ---------- OCR with confidence ----------

def ocr_with_confidence(img):
    text = pytesseract.image_to_string(img, lang="eng")
    data = pytesseract.image_to_data(img, lang="eng", output_type=pytesseract.Output.DICT)
    words = [(w, float(c)) for w, c in zip(data["text"], data["conf"])
             if w.strip() and float(c) >= 0]
    return text, words


def report(name, img, truth_lines, truth_fields):
    text, words = ocr_with_confidence(img)
    lines = clean_lines(text)
    ocr_fields = parse_fields(lines)
    joined = "\n".join(lines)

    similarity = difflib.SequenceMatcher(None, "\n".join(truth_lines), joined).ratio()
    exact = [k for k, v in truth_fields.items() if v in joined]
    mean_conf = sum(c for _, c in words) / len(words) if words else 0.0
    lowest = sorted(words, key=lambda wc: wc[1])[:5]

    print(f"=== {name} ===")
    print(f"Similarity:         {similarity:.3f}")
    print(f"Fields exact:       {len(exact)}/{len(truth_fields)}")
    print(f"Mean confidence:    {mean_conf:.1f}")
    print("Least confident:    " + ", ".join(f"'{w}' ({c:.0f})" for w, c in lowest))

    for key, value in truth_fields.items():
        if key in exact:
            continue
        match = difflib.get_close_matches(key, ocr_fields.keys(), n=1, cutoff=0.6)
        got = ocr_fields[match[0]] if match else "(field not found)"
        print(f"  WRONG  {key}: expected '{value}'  got '{got}'")
    print()


if __name__ == "__main__":
    truth_lines = clean_lines(text_layer(TEXT))
    truth_fields = parse_fields(truth_lines)
    base = render(SCAN, dpi=300)

    variants = [
        ("clean (300 dpi)", lambda img: img),
        ("low resolution (100 dpi)", low_res),
        ("blurred", blurred),
        ("speckled", speckled),
        ("tilted 3 degrees", tilted),
        ("everything at once", everything),
    ]
    for name, damage in variants:
        report(name, damage(base), truth_lines, truth_fields)
