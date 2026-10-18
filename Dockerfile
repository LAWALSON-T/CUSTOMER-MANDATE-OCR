# Airflow image for the Customer Mandate ETL, with OCR support for the mandate extractor.
# Replaces _PIP_ADDITIONAL_REQUIREMENTS, which reinstalled packages on every container start.
FROM apache/airflow:2.8.1-python3.11

USER root
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

USER airflow
COPY requirements-airflow.txt /tmp/requirements-airflow.txt
# Two guards against breaking Airflow:
#  - naming apache-airflow==2.8.1 stops pip from replacing Airflow itself;
#  - Airflow's official constraints keep the packages it depends on at tested versions.
#    Without them pip upgrades numpy 1.24 -> 2.x, which the image's pandas was not built for.
#    The cost: anthropic resolves to 0.40.0 (Airflow pins an older httpx). The extractor works with it.
ARG CONSTRAINTS=https://raw.githubusercontent.com/apache/airflow/constraints-2.8.1/constraints-3.11.txt
RUN pip install --no-cache-dir "apache-airflow==2.8.1" -r /tmp/requirements-airflow.txt -c "${CONSTRAINTS}"
