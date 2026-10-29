# Amont, registre des raccordements : image du serveur (home server aujourd'hui, serveur interne demain)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Europe/Paris

# poppler : pdftotext (lecture rapide des PDF) et pdftoppm (pages scannees envoyees en images au modele de vision)
RUN apt-get update \
    && apt-get install -y --no-install-recommends poppler-utils tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY amont_core ./amont_core
COPY static ./static
COPY 2026_09_18_amont_serveur.py 2026_09_18_amont_import.py 2026_09_18_amont_alertes.py \
     2026_09_18_amont_amorce.json 2026_10_07_amont_sources_import.py \
     2026_10_27_amont_extraits_cadastraux.py 2026_10_27_amont_tester_ia.py ./

EXPOSE 8000
CMD ["uvicorn", "amont_core.api:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
