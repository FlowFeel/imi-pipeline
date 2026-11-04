# Crossref deposit stub — stdlib only, no pip install, fully deterministic.
FROM python:3.12-alpine
COPY stub_crossref.py /app/stub_crossref.py
WORKDIR /app
EXPOSE 8000
HEALTHCHECK --interval=5s --timeout=3s --retries=10 \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/admin/health')"
CMD ["python", "stub_crossref.py"]
