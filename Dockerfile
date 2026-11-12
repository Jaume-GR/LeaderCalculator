FROM zookeeper:3.9

USER root

RUN apt-get update && \
    apt-get install -y python3 python3-venv && \
    rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /venv

RUN /venv/bin/pip install kazoo flask requests

ENV PATH="/venv/bin:$PATH"

WORKDIR /app

COPY main.py /app/main.py
COPY server.py /app/server.py
COPY start.sh /start.sh

RUN chmod +x /start.sh

ENTRYPOINT ["/start.sh"]