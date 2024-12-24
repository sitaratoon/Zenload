FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .

RUN python -m venv /opt/venv && \
    . /opt/venv/bin/activate && \
    pip install -r requirements.txt

COPY . .
ENV PATH="/opt/venv/bin:$PATH"

CMD ["python", "main.py"]