"""Step 5: Page quality gate, per-field confidence, exact labels, and a clean-up filter.

Run from the mandate-extractor folder with the venv active:
    python quality_ocr.py

The question this step answers:
    When OCR gets a field WRONG, do our checks flag it, or does it slip through as OK?
A wrong value marked OK is the only result that really hurts us. We count those.
"""
import re
from collections import OrderedDict

import pytesseract
from PIL import ImageFilter

# Reuse the loading and damage functions from step 4.
from stress_ocr import SCAN, TEXT, render, text_layer, clean_lines, parse_fields, \
    blurred, speckled, tilted

# The fields we expect on a mandate form. Labels are matched EXACTLY, never loosely.
LABELS = [
    "Bank", "Branch", "Account name", "Account type", "Date of form",
    "Signatory 1", "Signatory 2", "Signing rule", "Daily transaction limit",
]

# Starting guesses. We will set these from data, not from instinct.
PAGE_CONF_MIN = 85   # mean word confidence below this -> page goes to a person
FIELD_CONF_MIN = 80  # any word in a value below this -> field is flagged


# ---------- normalisation ----------

def normalise(value):
    """Deliberately narrow:
    1. collapse runs of whitespace into one space
    2. remove a space that sits between a digit separator and a digit ('500, 000' -> '500,000')
    Punctuation itself is never removed or changed: 500,000 and 500.000 must stay different.
    """
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r"(?<=\d)([,.])\s+(?=\d)", r"\1", value)
    return value


# ---------- OCR into lines of (word, confidence) ----------

def ocr_lines_with_conf(img):
    data = pytesseract.image_to_data(img, lang="eng", output_type=pytesseract.Output.DICT)
    lines = OrderedDict()
    for i, word in enumerate(data["text"]):
        conf = float(data["conf"][i])
        if not word.strip() or conf < 0:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(key, []).append((word, conf))
    return list(lines.values())


def page_confidence(lines):
    confs = [c for line in lines for _, c in line]
    return sum(confs) / len(confs) if confs else 0.0


# ---------- field extraction with exact labels ----------

def extract_fields(lines):
    """For each label, find the ONE line that starts exactly with 'Label:'.
    Zero matches -> MISSING. More than one -> AMBIGUOUS. Never guess."""
    results = {}
    for label in LABELS:
        prefix = label + ":"
        n_label_words = len(prefix.split())
        hits = [line for line in lines
                if " ".join(w for w, _ in line[:n_label_words]) == prefix]
        if not hits:
            results[label] = {"value": None, "min_conf": None, "status": "MISSING"}
            continue
        if len(hits) > 1:
            results[label] = {"value": None, "min_conf": None, "status": "AMBIGUOUS"}
            continue
        value_words = hits[0][n_label_words:]
        if not value_words:
            results[label] = {"value": None, "min_conf": None, "status": "MISSING"}
            continue
        value = normalise(" ".join(w for w, _ in value_words))
        min_conf = min(c for _, c in value_words)
        status = "OK" if min_conf >= FIELD_CONF_MIN else "LOW_CONF"
        results[label] = {"value": value, "min_conf": min_conf, "status": status}
    return results


# ---------- clean-up ----------

def despeckle(img):
    """A median filter replaces each pixel with the middle value of its neighbours.
    Isolated specks vanish; letter strokes, which are wider than one pixel, survive."""
    return img.filter(ImageFilter.MedianFilter(size=3))


# ---------- evaluation ----------

def evaluate(name, img, truth_fields):
    lines = ocr_lines_with_conf(img)
    page_conf = page_confidence(lines)
    gate = "PASS" if page_conf >= PAGE_CONF_MIN else "FAIL -> send to a person"
    fields = extract_fields(lines)

    counts = {"correct_ok": 0, "caught": 0, "slipped": 0, "false_alarm": 0}
    print(f"=== {name} ===")
    print(f"Page confidence: {page_conf:.1f}   Gate: {gate}")
    for label in LABELS:
        f = fields[label]
        expected = normalise(truth_fields.get(label, ""))
        correct = f["value"] == expected
        flagged = f["status"] != "OK"

        if correct and not flagged:
            counts["correct_ok"] += 1
            verdict = ""
        elif correct and flagged:
            counts["false_alarm"] += 1
            verdict = "  (flagged, but was actually right)"
        elif not correct and flagged:
            counts["caught"] += 1
            verdict = "  CAUGHT"
        else:
            counts["slipped"] += 1
            verdict = "  !!! SLIPPED THROUGH: wrong value marked OK"

        conf = "-" if f["min_conf"] is None else f"{f['min_conf']:.0f}"
        print(f"  {f['status']:<9} conf {conf:>3}  {label}: {f['value']!r}{verdict}")

    print(f"Summary: {counts['correct_ok']} right & OK, {counts['caught']} wrong & caught, "
          f"{counts['slipped']} wrong & SLIPPED, {counts['false_alarm']} false alarms")
    print()
    return counts


if __name__ == "__main__":
    truth_fields = parse_fields(clean_lines(text_layer(TEXT)))
    base = render(SCAN, dpi=300)
    worst = tilted(speckled(blurred(render(SCAN, dpi=150))))

    variants = [
        ("clean", base),
        ("speckled", speckled(base)),
        ("speckled + despeckle", despeckle(speckled(base))),
        ("everything at once", worst),
        ("everything + despeckle", despeckle(worst)),
    ]

    total_slipped = 0
    for name, img in variants:
        total_slipped += evaluate(name, img, truth_fields)["slipped"]

    print("=" * 50)
    print(f"Wrong values that slipped through as OK, across all variants: {total_slipped}")
    print(f"(thresholds: page {PAGE_CONF_MIN}, field {FIELD_CONF_MIN})")
