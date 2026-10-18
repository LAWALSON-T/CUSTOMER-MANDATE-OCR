"""Step 7: Better OCR for scans, and a gate that notices when OCR silently lost content.

Two fixes:
1. remove_lines(): erase long straight lines (table grids) before OCR.
   Letters are never 150 pixels of solid ink in a row, so they survive. Pages without lines are untouched.
2. ink coverage: what share of the page's dark pixels sit inside a word that OCR recognised.
   Confidence only describes the words OCR FOUND. Coverage tells us about the words it MISSED.
"""
import numpy as np
import pytesseract
from PIL import Image, ImageFilter

LINE_MIN_PX = 150   # a straight run of ink this long (at 300 dpi) is a ruled line, not a letter
DARK = 128          # pixel values below this count as ink


def _long_runs(dark, length):
    """True where a pixel lies inside a horizontal run of at least `length` dark pixels."""
    h, w = dark.shape
    cs = np.zeros((h, w + 1), np.int32)
    cs[:, 1:] = np.cumsum(dark, axis=1)
    full = (cs[:, length:] - cs[:, :-length]) == length   # window starting at column j is all ink
    fs = np.zeros((h, full.shape[1] + 1), np.int32)
    fs[:, 1:] = np.cumsum(full, axis=1)
    j = np.arange(w)
    hi = np.minimum(j, full.shape[1] - 1) + 1
    lo = np.clip(j - length + 1, 0, full.shape[1])
    return (fs[:, hi] - fs[:, lo]) > 0


def remove_lines(img, length=LINE_MIN_PX):
    a = np.array(img.convert("L"))
    dark = a < DARK
    lines = _long_runs(dark, length) | _long_runs(dark.T, length).T
    a = a.copy()
    a[lines] = 255
    return Image.fromarray(a)


def despeckle(img):
    return img.filter(ImageFilter.MedianFilter(size=3))


def rows_by_position(words):
    """Rebuild lines from where each word sits on the page, not from Tesseract's reading order.
    Tesseract may read a table column by column ('Bank, Branch, ...' then 'Example Savings Bank, ...'),
    which separates every label from its value. Grouping words whose vertical centres line up
    keeps each label on the same line as its value.
    Limitation: two side-by-side paragraphs of prose would be interleaved. Mandate forms are one column."""
    rows = []
    for w in sorted(words, key=lambda w: w["y"] + w["h"] / 2):
        centre = w["y"] + w["h"] / 2
        if rows and rows[-1]["top"] <= centre <= rows[-1]["bottom"]:
            row = rows[-1]
            row["words"].append(w)
            row["top"] = min(row["top"], w["y"])
            row["bottom"] = max(row["bottom"], w["y"] + w["h"])
        else:
            rows.append({"top": w["y"], "bottom": w["y"] + w["h"], "words": [w]})
    return [[(w["text"], w["conf"]) for w in sorted(r["words"], key=lambda w: w["x"])] for r in rows]


def ocr_page(img, psm):
    """OCR one image. Returns lines of (word, confidence), mean confidence and ink coverage."""
    data = pytesseract.image_to_data(img, lang="eng", config=f"--psm {psm}",
                                     output_type=pytesseract.Output.DICT)
    dark = np.array(img.convert("L")) < DARK
    inside = np.zeros_like(dark)
    words = []
    for i, word in enumerate(data["text"]):
        conf = float(data["conf"][i])
        if not word.strip() or conf < 0:
            continue
        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        inside[y:y + h, x:x + w] = True
        words.append({"text": word, "conf": conf, "x": x, "y": y, "w": w, "h": h})
    confs = [w["conf"] for w in words]
    return {
        "lines": rows_by_position(words),
        "page_conf": sum(confs) / len(confs) if confs else 0.0,
        "coverage": float(dark[inside].sum() / max(dark.sum(), 1)),
    }


def best_ocr(img):
    """Try raw and despeckled images, each with page modes 3 (auto) and 4 (one column,
    reads tables row by row). Keep the attempt that read the most of the page,
    then the most confident. Every attempt is recorded so the choice can be audited."""
    base = remove_lines(img)
    attempts = []
    for prep_name, prepped in (("raw", base), ("despeckle", despeckle(base))):
        for psm in (3, 4):
            result = ocr_page(prepped, psm)
            result["method"] = f"lines removed, {prep_name}, psm {psm}"
            attempts.append(result)
    best = max(attempts, key=lambda r: (round(r["coverage"], 2), r["page_conf"]))
    best["attempts"] = [{"method": r["method"], "coverage": round(r["coverage"], 3),
                         "page_conf": round(r["page_conf"], 1)} for r in attempts]
    return best


def tesseract_version():
    try:
        return str(pytesseract.get_tesseract_version())
    except Exception:
        return "unknown"
