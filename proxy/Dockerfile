FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir flask requests kazoo

COPY proxy.py .

CMD ["python", "-u", "proxy.py"]