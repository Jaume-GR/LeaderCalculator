#!/bin/bash

# Iniciar ZooKeeper
/docker-entrypoint.sh zkServer.sh start-foreground &
ZK_PID=$!

# Iniciar Python
python3 -u /app/main.py &
PY_PID=$!

# Al terminar, detener ambos procesos
trap 'kill "$ZK_PID" "$PY_PID" 2>/dev/null || true' EXIT

# Esperar hasta que uno de los dos termine
wait -n "$ZK_PID" "$PY_PID"

# Provocar reinicio del contenedor
exit 1
