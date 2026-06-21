FROM python:3.11-slim

# Librairies systeme requises par WeasyPrint (rendu PDF serveur). Sur Debian elles
# s'installent aux emplacements standards -> ctypes.util.find_library les trouve
# (ce que Nixpacks ne garantissait pas : echec "libgobject-2.0-0 introuvable").
RUN apt-get update && apt-get install -y --no-install-recommends \
        libglib2.0-0 \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libharfbuzz0b \
        libfontconfig1 \
        libcairo2 \
        libgdk-pixbuf-2.0-0 \
        libffi8 \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Railway fournit $PORT ; defaut 8000 en local.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
