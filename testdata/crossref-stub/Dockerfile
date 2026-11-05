# Hermetic Crossref Schema 5.3.1 Simulator Container
FROM python:3.12-alpine
COPY crossref_simulator.py /app/crossref_simulator.py
COPY stub_crossref.py /app/stub_crossref.py
WORKDIR /app
EXPOSE 8000
HEALTHCHECK --interval=5s --timeout=3s --retries=10 \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/admin/health')"
CMD ["python", "stub_crossref.py"]
