'''
 Servidor HTTP Calculadora REST
 Atiende y gestiona un servidor HTTP y sus peticiones
 Proporciona una interfaz de delegación de trabajo
 por parte del líder a los trabajadores mediante un endpoint.
'''
from flask import Flask, request, jsonify, session
import statistics
import requests
import logging
import random
import math
import uuid
import sys

log = logging.getLogger("calculadora")
log.setLevel(logging.INFO)
log.propagate = False

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter("%(asctime)s [CALC] %(message)s", datefmt="%d/%m %H:%M:%S"))
log.addHandler(handler)

class Server:
    EXCLUDE_LEADER_FROM_WORKING = True
    MAX_ARG_NUM = 10 # límite ficticio (funciona con más argumentos)
    instructions = { # op : [argmin, argmax]
        "add" : [2, MAX_ARG_NUM],
        "sub" : [2, MAX_ARG_NUM],
        "mult": [2, MAX_ARG_NUM],
        "div" : [2, MAX_ARG_NUM],
        "sqrt": [1, 1],
        "mean": [2, MAX_ARG_NUM],
        "std" : [2, MAX_ARG_NUM],
        "rst" : [0, 0]
    }
    operations = list(instructions.keys())

    def __init__(self, znode_id, zk, leader = False):
        self.znode_id = znode_id
        self.zk = zk
        self.leader = leader
        self.app = Flask(__name__)
        self.app.secret_key = "sk"

        @self.app.route("/api/v1/calc", methods=["POST"])
        def get_solution():
            try:
                if self.leader:
                    # Escoge un trabajador al azar y le manda la petición
                    worker_hostname = self.worker_routing()
                    resp = requests.post(f"http://{worker_hostname}/internal/worker_calc", json=request.get_json(), timeout=5)
                    return jsonify(resp.json()), resp.status_code
                else:
                    return jsonify({"ok" : False, "error": f"Error: el proxy ha enviado una peticion a un worker"})
            except requests.RequestException:
                return jsonify({"ok": False, "error": "Worker no disponible"}), 503

        @self.app.route("/internal/worker_calc", methods=["POST"])
        def worker_calc():
            if self.EXCLUDE_LEADER_FROM_WORKING and self.leader:
                ok = False
                arg = "worker_calc(): este nodo es lider!"
            else:
                ok = True
                arg = None
                data = request.get_json()
                if data["op"] == "rst":
                    arg = 0
                else:
                    ok, arg = self.command_processor(data)
                    if ok: # Limitamos los resultados a 3 decimales por cuestiones de legibilidad
                        arg = round(arg, 3)
                        if isinstance(arg, float) and arg.is_integer(): arg = int(arg)
            respuesta = {"ok": ok, "result" if ok else "error" : arg if ok else f"Error: {arg}"}
            log.info(f'REQUEST ({data["op"]} {" ".join(f"{x:.2f}" for x in data["args"])}) -> {respuesta}')
            return jsonify(respuesta)
            
    # Obtiene los nodos candidatos y escoge uno al azar
    def worker_routing(self):
        children = self.zk.get_children("/eleccion")
        # log.info(f"all znodes {children}\n")
        workers = [x for x in children if x != self.znode_id] if self.EXCLUDE_LEADER_FROM_WORKING else children
        # log.info(f"all workers {workers}\n")
        worker = random.choice(list(workers))
        log.info(f"random worker: {worker}")
        worker_hostname = self.zk.get("/eleccion/" + worker)[0].decode()
        log.info(f"redirecting request to worker {worker_hostname}")
        return worker_hostname

    def run(self):
        self.app.run(host="0.0.0.0", port=5000, use_reloader=False)

    def set_leader(self, leader):
        self.leader = leader
        
    def command_processor(self, data):
        op = data["op"]
        if op == None:
            return (False, f"No se ha seleccionado ninguna operacion")
        elif op not in self.operations:
            return (False, f"la operacion '{op}' no existe o no se encuentra implementada")
        numeros = data["args"]
        if not(numeros != None and isinstance(numeros, list) and all(type(x) in (int, float) for x in numeros)):
            return (False, f"la lista de operando/s {numeros} no es valida")
        elif not numeros:
            return (False, f"No se ha porporcionado ningun operando!")
        argmin = self.instructions[op][0]
        argmax = self.instructions[op][1]
        if len(numeros) < argmin : return (False, f"la instruccion requiere de como minimo 2 argumentos (numeros), [{op} arg1 arg2]")
        if len(numeros) > argmax : return (False, f"demasiados argumentos! [{op} arg1{f' ... arg{argmax}' if argmax > 1 else ''}]")
        
        if op == "add" : return (True, sum(data["args"]))
        if op == "sub" : return (True, numeros[0] - sum(numeros[1:]))
        if op == "mult": return (True, numeros[0] * numeros[1])
        if op == "div" :
            if numeros[1] == 0: return (False, "se esta intentando dividir por 0 (infinito)")
            else : return (True, numeros[0] / numeros[1])
        if op == "sqrt" :
            if numeros[0] < 0: return (False, "la raiz cuadrada se debe hacer sobre un numero positivo")
            else : return (True, math.sqrt(numeros[0]))
        if op == "mean" : return (True, sum(numeros) / len(numeros))
        if op == "std"  : return (True, statistics.pstdev(numeros)) # Desviación poblacional