## Mandate form extraction (upgrade, October 2026)

The pipeline now also **reads** each customer's account mandate form. A mandate form is the instruction that says who may sign on an account, under what rule, and up to what daily limit. Until now the ETL stored these files as opaque binary data. The upgrade turns each form into verified fields, checks them against the customer record, and sends anything doubtful to a person.

The core rule: **the model's answer is a claim, and code checks every claim.** A field the code cannot verify comes back as `null` with a reason. It is never guessed.

### What changed

| Area | Before | After |
|---|---|---|
| Documents per customer | ID, proof of address, signature | + `mandate_form` (new column `mandate_form_path`) |
| Reading the form | Not read | OCR if needed, model extracts fields with exact quotes, code verifies |
| Duplicate loads | `insert_one`, duplicates possible | `replace_one(..., upsert=True)` + unique index on `customer_id` |
| Missing files | Customer marked `processed` anyway | Marked `incomplete`; missing files listed in `metadata.missing_documents` |
| Status write-back errors | Swallowed; batch loop could repeat forever | Raised; run stops. Hard cap of 500 batches per run |
| Connections | New client per customer / per batch | One per run |
| `verify_load` | Counted documents | Compares MySQL with MongoDB; fails the run if a loaded customer is missing |
| Report | Always printed `SUCCESS` | `OK` only when nothing needs attention, otherwise lists what does |
| Credentials | Hard-coded in `db_utils.py`, compose file, `start.bat` | All in `.env` (not committed); `.env.example` documents them |
| Airflow image | Packages reinstalled at every start | Built once from `Dockerfile`, with Tesseract OCR |

### How a form is processed

```
run_etl_pipeline  →  extract_mandate_forms  →  verify_load  →  generate_report
```

Extraction is its own task, after the load. A slow or failed model call therefore never marks a customer `failed` in MySQL, and it is retried on the next run.

For each newly loaded form, `extract_mandate_forms`:

1. **Reads the text.** If the PDF has a text layer, uses it. If it is a scan, renders the page and runs Tesseract. Before OCR it removes ruled table lines (they made Tesseract lose a whole table), tries raw and despeckled images with two page modes, and keeps the attempt that read the most of the page. It then rebuilds lines from word positions, so a label stays on the same line as its value.
2. **Checks page quality.** Mean OCR confidence must be at least 85, and at least 90% of the page's ink must sit inside recognised words. Confidence alone missed a page that had lost its whole table (confidence 89, ink coverage 21%).
3. **Asks the model** for nine fields, each with the exact quote it came from. The document is passed as untrusted data.
4. **Verifies every field in code.** The quote must appear in the document text and the value must appear inside the quote. OCR must have been confident about the value's words. The quote may not come only from a customer-written remarks line. If the document contains more than one amount, the daily limit is marked as a conflict.
5. **Cross-checks against MySQL.** The customer's name must be one of the signatories on the form.
6. **Decides.** `auto_accept` only if every gate and every field passed. Otherwise `needs_review`, with the reasons listed. Processing failures are `error` and are retried up to 3 times.

The result is stored in the customer's MongoDB document under `mandate_extraction`: fields, statuses, reasons, the OCR text, OCR confidence and coverage, the model name and the Tesseract version.

### Decision rules I chose

- **Remarks.** Any form with a customer remarks line goes to review (`MANDATE_REMARKS_POLICY=review_all`). The alternative, `review_if_relevant`, only flags remarks that mention a field or an amount. [TO FILL: why you chose this, in your own words.]
- **Thresholds.** Page confidence 85, field confidence 80, ink coverage 90%. These were set from the synthetic test forms, not from real scans. They need re-checking on real documents and on the Tesseract version in use.

### Running it

```
copy .env.example .env        # then fill in values; see the comments in the file
docker compose build
docker compose up -d
docker exec airflow_scheduler python /opt/airflow/scripts/migrate_upgrade.py            # dry run
docker exec airflow_scheduler python /opt/airflow/scripts/migrate_upgrade.py --apply    # add column, dedupe, unique index
docker exec -w /opt/airflow/scripts airflow_scheduler python generate_mandate_forms.py # 10 sample forms
```

Then trigger `customer_mandate_etl` in Airflow (http://localhost:8081).

MySQL is published on host port **3307**, not 3306, so it does not clash with a local MySQL server. Inside Docker the services still use `mysql:3306`.

`generate_mandate_forms.py` writes a manifest (`source_files/customer_documents/mandate_forms_manifest.json`) listing the expected outcome of every form. Two forms are deliberate traps.

### Results

**Standalone extractor tests** (repo: [TO FILL: link to mandate-extractor]):

- 8 forms in 4 layouts (standard labels, different labels, a table, a letter with no labels), each as text and as scan: no wrong value was auto-accepted. A label-matching baseline found 0 of 9 fields on the three non-standard layouts; the model found all 9 on every text version.
- Attack forms with planted remarks, tested with a simulated model that falls for the attack: 4 of 4 wrong values got through with the defences off, 0 with them on. The real model resisted both attacks. The fake-limit form still went to review, which is how the attempt becomes visible.

**First pipeline run (18 October 2026, 10 customers with forms):**

| Outcome | Customers | Why |
|---|---|---|
| auto_accept | CUST001, CUST002, CUST0001, CUST0002, CUST0004 | All checks passed |
| needs_review (trap) | CUST003 | Customer name not a signatory on the form |
| needs_review (trap) | CUST005 | Fake limit in remarks; two different amounts |
| needs_review (false alarm) | CUST0005 | OCR unsure of a word in the branch name |
| error, retried | CUST0003, CUST004 | `APIConnectionError`: network, request never reached the model |

[TO FILL: result of the retry run for CUST0003 and CUST004.]

Load status for the same run: 5 `processed`, 5 `incomplete`. The 5 `incomplete` customers are volume-test customers whose generated document paths do not match real files (see Limitations). MySQL and MongoDB agreed: 1,005 documents for 1,005 customers.

**Wrong values auto-accepted, across every test above: 0.** That is a small synthetic sample, not proof.

### Limitations

- **Synthetic data only.** All forms are generated, typed, clean and one page. Handwriting, stamps, signatures, photocopies, multi-page forms and real layout variety are untested.
- **Signatures lower ink coverage.** A real form's signature is ink but not text, so the coverage gate would send it to review. Signature boxes would need to be excluded.
- **Single-column assumption.** Lines are rebuilt from word positions; two paragraphs side by side would be interleaved.
- **Remarks detection is one line.** A remarks section that wraps to a second line is not recognised. An injected instruction for a non-amount field that does not start with "Remarks"/"Note"/"Comment" is not caught.
- **Amount conflict raises false alarms** on genuine forms that carry two amounts (for example a per-transaction and a daily limit).
- **OCR differs by version.** The container runs Tesseract 5.3.0; development used 5.5.3. The same form gets different confidence scores, so thresholds must be checked on the version deployed. Every result records the version used.
- **Names.** Tesseract's English model is less confident on Nigerian names (for example "Ngozi", "Ifeoma"), causing false alarms. Names with tone marks were not tested.
- **Data leaves the machine.** Form text is sent to an external model API. Acceptable for synthetic data. Real customer forms would need data-protection approval or a model hosted inside the bank.
- **Dependency pins.** Airflow 2.8.1's constraints force `anthropic` 0.40.0 and `numpy` 1.24. Without them, pip upgrades numpy to 2.x, which the image's pandas was not built for.
- **Volume-test paths** (existing limitation): most generated document paths do not match real files, which is why those customers load as `incomplete`.
