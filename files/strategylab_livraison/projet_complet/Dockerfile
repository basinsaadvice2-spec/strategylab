FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt
COPY . .
# Le serveur ne tourne pas en root
RUN useradd --create-home app && chown -R app /app
USER app
# Cloud Run fournit le port dans la variable PORT (8080 par défaut)
CMD ["python", "-m", "api.server"]
