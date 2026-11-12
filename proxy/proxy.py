"""
Servicio Proxy

Proporciona una dirección de enlace fija independiente del líder
Redirecciona las peticiones HTTP enviadas por los clientes al líder del servicio
Gestiona e imprime las métricas del estado de las peticiones recibidas.
"""
from flask import Flask, request, jsonify, Response
from kazoo.client import KazooClient, KazooState
from kazoo.exceptions import NoNodeError
from time import perf_counter, time, ctime
from collections import Counter
from threading import Lock
import requests
import logging
import sys
import os

# Loggers
log = logging.getLogger("proxy_app")
log.setLevel(logging.INFO)
log.propagate = False
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter("%(asctime)s [PROXY] %(message)s", datefmt="%d/%m %H:%M:%S"))
log.addHandler(handler)

metlog = logging.getLogger("proxy.stats")
metlog.setLevel(logging.INFO)
metlog.propagate = False
met_handler = logging.StreamHandler(sys.stdout)
met_handler.setFormatter(logging.Formatter("# %(message)s"))
metlog.addHandler(met_handler)

# Decide si se regista None en el log de líderes y si se imprime cuando el líder se autodestruye y el proxy no apunta a nadie
APPEND_LEADER_TRANSITION = False

metlock = Lock()
metrics = {
    "req_received": 0,
    "req_attended": 0,
    "req_failed": 0,
    "resp_times": [],
    "req_leader": Counter(), # Counter permite mantener un contador para cada nodo de forma cómoda
    "log_leader": []
}

#percentil 99 tiempo respuesta

app = Flask(__name__)

leader = None

# Nos conectamos a cualquiera de los servidores de ZooKeeper
zk = KazooClient(hosts=os.environ["ZK_HOSTS"])
zk.start()

@zk.DataWatch("/leader")
def update_leader(data, stat):
    global leader
    new_leader = data.decode() if data is not None else None

    if new_leader != leader:
        leader = new_leader
        if new_leader is not None or APPEND_LEADER_TRANSITION:
            with metlock: metrics["log_leader"].append((time(), leader))
            log.warning(f"(!): Lider actualizado, redireccionando peticiones a {leader}.\n")

@app.route("/api/v1/calc", methods=["POST"])
def proxy():
    log.info("")
    log.info(f"Peticion recibida: {request.get_json()}")
    
    start = perf_counter()
    with metlock: metrics["req_received"] += 1

    target_leader = leader 

    if target_leader is None:
        with metlock:
            metrics["req_failed"] += 1
            metrics["resp_times"].append(perf_counter() - start)
        return jsonify({"ok": False, "error": "Error: No hay líder asignado (None)"})
    try:
        r = requests.post(f"http://{target_leader}/api/v1/calc", json=request.get_json(), timeout=5)
        with metlock:
            if r.status_code < 400: # Los códigos de error se encuentran por encima de 400
                metrics["req_attended"] += 1
            else:
                metrics["req_failed"] += 1
            metrics["req_leader"][target_leader] += 1
        return jsonify(r.json())

    except requests.RequestException:
        with metlock: metrics["req_failed"] += 1
        return jsonify({"ok": False, "error": "Error: Lider no disponible"})

    finally:
        if target_leader is not None:
            with metlock: metrics["resp_times"].append(perf_counter() - start)

@app.route("/api/v1/metrics", methods=["POST"])
def print_metrics():
    met = None
    with metlock: met = metrics
    log_leader = met["log_leader"]
    req_leader = met["req_leader"]
    resp_times = met["resp_times"]
    metlog.info("")
    metlog.info("#"*100)
    metlog.info("")
    metlog.info("___________Leadership timeline___________")
    for t, leader in log_leader: metlog.info(f"{ctime(t)} | {leader}")
    metlog.info("")
    mean_resp_time = round(sum(resp_times) / len(resp_times), 3) if resp_times else 0
    metlog.info(f"Mean Response Time = {mean_resp_time}s")
    metlog.info("")
    metlog.info("______REQUESTS______")
    metlog.info(f"Attended: {met["req_attended"]}")
    metlog.info(f"Failed:   {met["req_failed"]}")
    metlog.info(f"Total Received: {met["req_received"]}")
    metlog.info("")
    graph_len = 40
    ratio = graph_len / max(req_leader.values()) if req_leader else 0
    metlog.info("")
    metlog.info("Leader Request Distribution")
    metlog.info(f"       {"_" * (graph_len + 1)}")
    metlog.info("")
    for name, qty in req_leader.items():
        metlog.info(f"{name.split(':')[0]} | {"#" * round(qty * ratio)} ({qty})")
    metlog.info(f"       {"_" * (graph_len + 1)}")
    metlog.info("")
    metlog.info("#"*100)
    metlog.info("")
    return jsonify({"ok": True})

@app.route("/api/v1/reset_metrics", methods=["POST"])
def reset_metrics():
    global metrics
    with metlock:
        metrics = {
            "req_received": 0,
            "req_attended": 0,
            "req_failed": 0,
            "resp_times": [],
            "req_leader": Counter(),
            "log_leader": []
        }
        # Si reiniciamos las métricas al iniciar el experimento y justo había un líder
        # ya escogido nos aseguramos de que este entre en el historial
        if leader is not None: metrics["log_leader"].append((time(), leader))
    return jsonify({"ok" : True})
    
# Permitimos que flask escuche todas las interfaces de red
app.run(host="0.0.0.0", port=5000)