"""Mandate form extraction for the Customer Mandate ETL.

Runs as its own Airflow task AFTER the load, so a slow or failed model call never marks a
customer 'failed' in MySQL. It looks for MongoDB customer documents that contain a document
with category 'mandate_form' and no finished extraction, runs the extractor on the stored bytes,
and writes the result back into that customer document under 'mandate_extraction'.

Statuses written to mandate_extraction.status:
    auto_accept   every field verified, every gate passed
    needs_review  something needs a person; mandate_extraction.review_reasons says what
    error         processing failed; retried on later runs, up to MAX_ATTEMPTS
"""
import io
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image
from pymongo import MongoClient

sys.path.insert(0, str(Path(__file__).parent / "mandate_extractor"))
import extract                                   # noqa: E402  (the standalone extractor)
from ocr_tools import best_ocr, tesseract_version  # noqa: E402
from quality_ocr import normalise                 # noqa: E402

BATCH_LIMIT = 50     # bounds the cost and duration of one run
MAX_ATTEMPTS = 3     # stop retrying a document that keeps failing; it then needs a person
IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}

# What to do when a form has a customer-written remarks line. A business decision:
#   "review_all"         any remarks line sends the record to a person (safest)
#   "review_if_relevant" only remarks that mention a field or an amount do
REMARKS_POLICY = os.environ.get("MANDATE_REMARKS_POLICY", "review_all")
RELEVANT_REMARK = re.compile(
    r"limit|sign|signator|mandate|operation|account|amount|NGN|₦|\d{1,3}(,\d{3})+", re.IGNORECASE)


def mongo_collection():
    client = MongoClient(
        host=os.environ.get("MONGO_HOST", "mongodb"), port=27017,
        username=os.environ["MONGO_USER"], password=os.environ["MONGO_PASSWORD"],
        serverSelectionTimeoutMS=10_000)
    db = client[os.environ.get("MONGO_DATABASE", "customer_mandates")]
    return client, db["customer_mandates"]


# ---------- reading stored bytes ----------

def read_bytes(data, filename):
    """PDF -> the extractor's normal path (text layer or OCR). Image -> OCR directly."""
    suffix = Path(filename).suffix.lower()
    if suffix in IMAGE_TYPES:
        best = best_ocr(Image.open(io.BytesIO(data)).convert("L"))
        best["source"] = f"OCR of image ({best['method']})"
        return best
    if suffix != ".pdf":
        raise ValueError(f"unsupported mandate form type: {suffix}")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "form.pdf"
        path.write_bytes(data)
        return extract.read_document(path)


# ---------- checks that use what the ETL already knows ----------

def customer_name_check(customer, fields):
    """The customer in MySQL should be one of the signatories on the form."""
    info = customer.get("personal_info") or {}
    name = normalise(f"{info.get('first_name', '')} {info.get('last_name', '')}").lower()
    signatories = [(fields[k].get("value") or "").lower() for k in ("signatory_1", "signatory_2")]
    if not name.strip():
        return "customer record has no name to compare with"
    if name not in signatories:
        return f"customer name '{name}' is not one of the signatories on the form"
    return None


def remarks_check(untrusted_lines):
    if not untrusted_lines:
        return None
    if REMARKS_POLICY == "review_if_relevant":
        relevant = [l for l in untrusted_lines if RELEVANT_REMARK.search(l)]
        return f"remarks mention mandate details: {relevant}" if relevant else None
    return f"form has customer remarks: {untrusted_lines}"


# ---------- one form ----------

def extract_form(customer, form_doc):
    doc = read_bytes(form_doc["binary_data"], form_doc.get("metadata", {}).get("filename", "form.pdf"))
    text = extract.lines_to_text(doc["lines"])
    ctx = extract.build_context(doc["lines"])
    claims = extract.call_model(text)
    fields = {key: extract.verify(key, claims.get(key), ctx) for key in extract.FIELDS}

    reasons = []
    if doc["page_conf"] < extract.PAGE_CONF_MIN:
        reasons.append(f"page confidence {doc['page_conf']:.1f} below {extract.PAGE_CONF_MIN}")
    if doc["coverage"] < extract.COVERAGE_MIN:
        reasons.append(f"only {doc['coverage']:.0%} of the page's ink was read")
    for key, f in fields.items():
        if f["status"] != "OK":
            reasons.append(f"{key}: {f['status']} ({f.get('reason', '')})")
    for check in (customer_name_check(customer, fields), remarks_check(ctx["untrusted_lines"])):
        if check:
            reasons.append(check)

    return {
        "status": "auto_accept" if not reasons else "needs_review",
        "review_reasons": reasons,
        "fields": fields,
        "source": doc["source"],
        "page_conf": round(doc["page_conf"], 1),
        "coverage": round(doc["coverage"], 3),
        "untrusted_lines": ctx["untrusted_lines"],
        "ocr_text": text,
        "model": extract.MODEL,
        "tesseract": tesseract_version(),
        "remarks_policy": REMARKS_POLICY,
        "extracted_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------- the Airflow entry point ----------

def run_extraction(limit=BATCH_LIMIT):
    """Process up to `limit` customers with an unextracted mandate form. Returns counts."""
    counts = {"auto_accept": 0, "needs_review": 0, "error": 0}
    client, coll = mongo_collection()
    try:
        query = {
            "documents.category": "mandate_form",
            "$or": [
                {"mandate_extraction": {"$exists": False}},
                {"mandate_extraction.status": "error",
                 "mandate_extraction.attempts": {"$lt": MAX_ATTEMPTS}},
            ],
        }
        for customer in coll.find(query).limit(limit):
            form = next(d for d in customer["documents"] if d.get("category") == "mandate_form")
            attempts = (customer.get("mandate_extraction") or {}).get("attempts", 0) + 1
            try:
                result = extract_form(customer, form)
            except Exception as e:  # never let one form stop the batch
                result = {"status": "error", "error": f"{type(e).__name__}: {e}",
                          "extracted_at": datetime.now(timezone.utc).isoformat()}
                if attempts >= MAX_ATTEMPTS:
                    result["review_reasons"] = [f"extraction failed {attempts} times; needs a person"]
            result["attempts"] = attempts
            # Update by _id, so the result lands on exactly the document it was read from.
            coll.update_one({"_id": customer["_id"]}, {"$set": {"mandate_extraction": result}})
            counts[result["status"]] += 1
            print(f"{customer.get('customer_id')}: {result['status']}"
                  + (f"  {result.get('review_reasons') or result.get('error', '')}"
                     if result["status"] != "auto_accept" else ""))
    finally:
        client.close()
    print(f"Mandate extraction: {counts}")
    return counts
