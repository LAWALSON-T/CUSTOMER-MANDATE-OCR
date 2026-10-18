-- Mandate form extraction upgrade.
-- Runs automatically only on a brand-new MySQL volume, after 01_init_schema.sql.
-- For an existing database, run python-scripts/migrate_upgrade.py instead.
ALTER TABLE customer_mandates
    ADD COLUMN mandate_form_path VARCHAR(500) NULL AFTER signature_path;
