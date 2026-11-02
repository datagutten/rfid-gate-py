FROM python:3.15
RUN pip install -U pip prometheus-client flask requests

WORKDIR /app
COPY *.py /app
COPY feig /app/feig