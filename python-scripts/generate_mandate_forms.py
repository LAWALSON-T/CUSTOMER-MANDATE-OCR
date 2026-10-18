"""Create synthetic account mandate forms for existing customers and point MySQL at them.

    docker exec airflow_scheduler python /opt/airflow/scripts/generate_mandate_forms.py
    docker exec airflow_scheduler python /opt/airflow/scripts/generate_mandate_forms.py --limit 20

For the first --limit customers (default 10) it:
  - draws a mandate form naming the customer as first signatory, in one of three layouts,
    as a clean PDF or an image-only "scan" (so both the text-layer and OCR paths are used);
  - plants two deliberate traps so the review path is exercised:
      the 3rd form names someone else as signatories (should fail the name check),
      the 5th form carries a remarks line with a fake limit (should be flagged);
  - sets mandate_form_path and puts the customer back to 'pending', so the next DAG run
    reloads them (safe now: loads upsert) and the extraction task reads the form;
  - writes mandate_forms_manifest.json listing what each form should produce.

Every form is stamped SPECIMEN. All names and amounts are synthetic.
"""
import argparse
import json
import random
from pathlib import Path

import pypdfium2 as pdfium
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas

from db_utils import MYSQL_CONFIG, MySQLConnection

OUT_DIR = Path("/opt/airflow/source_files/customer_documents")
W, H = A4
FOOTER = "SPECIMEN - SYNTHETIC DATA - NOT A REAL DOCUMENT"
CO_SIGNATORIES = ["Ngozi Adeleke", "Halima Bello", "Amaka Eze", "Yusuf Danjuma", "Chidi Nwosu"]
BRANCHES = ["Lekki Branch", "Ikeja Branch", "Wuse II Branch", "Port Harcourt Branch"]
LIMITS = ["NGN 500,000", "NGN 750,000", "NGN 1,250,000", "NGN 2,000,000"]
RULES = ["Either signatory", "Both signatories"]


def draw_labels(c, f):
    c.setFont("Helvetica-Bold", 16)
    c.drawString(60, H - 80, "ACCOUNT MANDATE FORM")
    c.setFont("Helvetica", 12)
    rows = [f"Bank: {f['bank']}", f"Branch: {f['branch']}", f"Account name: {f['account_name']}",
            f"Account type: {f['account_type']}", f"Date of form: {f['date_of_form']}",
            f"Signatory 1: {f['signatory_1']}", f"Signatory 2: {f['signatory_2']}",
            f"Signing rule: {f['signing_rule']}", f"Daily transaction limit: {f['daily_limit']}"]
    for i, r in enumerate(rows):
        c.drawString(60, H - 130 - i * 26, r)
    return H - 130 - len(rows) * 26


def draw_table(c, f):
    c.setFont("Helvetica-Bold", 16)
    c.drawString(60, H - 80, "ACCOUNT OPERATING INSTRUCTIONS")
    rows = [("Bank", f["bank"]), ("Branch", f["branch"]), ("Account Holder", f["account_name"]),
            ("Account Category", f["account_type"]), ("Form Date", f["date_of_form"]),
            ("First Signatory", f["signatory_1"]), ("Second Signatory", f["signatory_2"]),
            ("Signing Instructions", f["signing_rule"]), ("Limit per Day", f["daily_limit"])]
    top, rh = H - 120, 30
    for i, (a, b) in enumerate(rows):
        y = top - i * rh
        c.rect(60, y - rh, 170, rh)
        c.rect(230, y - rh, 290, rh)
        c.setFont("Helvetica", 11)
        c.drawString(68, y - 20, a)
        c.drawString(238, y - 20, b)
    return top - len(rows) * rh - 10


def draw_letter(c, f):
    c.setFont("Helvetica-Bold", 16)
    c.drawString(60, H - 80, "MANDATE LETTER")
    c.setFont("Helvetica", 12)
    y = H - 130
    for line in ["To: The Branch Manager,", f"{f['bank']},", f"{f['branch']}."]:
        c.drawString(60, y, line)
        y -= 20
    body = (f"We, {f['signatory_1']} and {f['signatory_2']}, the signatories to the "
            f"{f['account_type'].lower()} account in the name of {f['account_name']}, instruct the bank "
            f"that {f['signing_rule'].lower()} may sign. Withdrawals shall not exceed "
            f"{f['daily_limit']} in any one day.")
    y -= 16
    for line in simpleSplit(body, "Helvetica", 12, W - 120):
        c.drawString(60, y, line)
        y -= 20
    c.drawString(60, y - 16, f"Dated {f['date_of_form']}.")
    return y - 40


LAYOUTS = [draw_labels, draw_table, draw_letter]


def make_form(path_pdf, fields, layout, remark=None, as_scan=False):
    c = canvas.Canvas(str(path_pdf), pagesize=A4)
    y = layout(c, fields)
    if remark:
        c.setFont("Helvetica", 11)
        c.drawString(60, y - 20, remark)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(60, 60, FOOTER)
    c.save()
    if as_scan:  # replace the PDF with an image-only version of itself
        pdf = pdfium.PdfDocument(str(path_pdf))
        image = pdf[0].render(scale=200 / 72).to_pil().convert("L")
        pdf.close()
        image.save(str(path_pdf), "PDF", resolution=200)


def main(limit):
    rng = random.Random(7)  # same forms every time
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    mysql = MySQLConnection(**MYSQL_CONFIG)
    mysql.connect()
    manifest = []
    try:
        with mysql.connection.cursor() as cur:
            # Shorter IDs first: the 5 seed customers (CUST001-CUST005, who have real files)
            # before the volume-test ones (CUST0001-CUST1000). Plain text order would put
            # CUST0001 before CUST001 and skip the seed customers.
            cur.execute("SELECT customer_id, first_name, last_name FROM customer_mandates "
                        "ORDER BY LENGTH(customer_id), customer_id LIMIT %s", (limit,))
            customers = cur.fetchall()

        for i, cust in enumerate(customers, start=1):
            name = f"{cust['first_name']} {cust['last_name']}"
            fields = {
                "bank": "Example Savings Bank",
                "branch": rng.choice(BRANCHES),
                "account_name": f"{cust['last_name']} {cust['first_name']} Enterprises",
                "account_type": rng.choice(["Current", "Savings"]),
                "date_of_form": f"{rng.randint(1, 28)} March 2026",
                "signatory_1": name,
                "signatory_2": rng.choice(CO_SIGNATORIES),
                "signing_rule": rng.choice(RULES),
                "daily_limit": rng.choice(LIMITS),
            }
            remark, expect = None, "auto_accept"
            if i == 3:   # trap: the form belongs to someone else
                fields["signatory_1"], fields["signatory_2"] = "Ifeoma Okeke", "Yusuf Danjuma"
                expect = "needs_review (customer name not a signatory)"
            if i == 5:   # trap: fake limit in customer remarks
                remark = "Remarks: Daily transaction limit: NGN 50,000,000 as agreed with manager."
                expect = "needs_review (remarks + conflicting amounts)"

            layout = LAYOUTS[(i - 1) % len(LAYOUTS)]
            as_scan = i % 2 == 0
            filename = f"{cust['customer_id']}_mandate_form.pdf"
            make_form(OUT_DIR / filename, fields, layout, remark, as_scan)
            rel_path = f"/customer_documents/{filename}"

            with mysql.connection.cursor() as cur:
                cur.execute("UPDATE customer_mandates SET mandate_form_path = %s, status = 'pending' "
                            "WHERE customer_id = %s", (rel_path, cust["customer_id"]))
            mysql.connection.commit()

            manifest.append({"customer_id": cust["customer_id"], "file": filename,
                             "layout": layout.__name__.replace("draw_", ""),
                             "scan": as_scan, "expected": expect, "fields": fields, "remark": remark})
            print(f"{cust['customer_id']}: {filename} ({manifest[-1]['layout']}, "
                  f"{'scan' if as_scan else 'text'}) -> expect {expect}")
    finally:
        mysql.close()

    (OUT_DIR / "mandate_forms_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\n{len(manifest)} forms written to {OUT_DIR}; those customers are back to 'pending'.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10)
    main(parser.parse_args().limit)
