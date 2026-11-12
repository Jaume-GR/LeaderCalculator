"""
Main.py

Recibe a los contenedores que proporcionan el servicio de Zookeeper
y gestiona su znodo representante.
Gestiona también la asignación automática de los líderes,
su autodestrucción y la inicialización del servicio calculadora.
"""
import os
import time
import random
from kazoo.client import KazooClient
import threading
from server import Server
import socket
import logging
import sys

log = logging.getLogger("main")
log.setLevel(logging.INFO)
log.propagate = False

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter(
    "%(asctime)s [MAIN] %(message)s",
    datefmt="%d/%m %H:%M:%S"
))
log.addHandler(handler)

# etcd para redirigir las solicitudes al líder (?)
# sino un script de python a modo de proxy.
# posible problema de sobrecarga en esta arquitectura (?) (justificar)

# Si el líder está caído no tiene por qué atender a la petición (se pueden perder peticiones),
# sin embargo debe quedar constancia de que ha llegado una petición y no se ha podido atender,
# quizás se pueda registrar en un 6to contenedor donde se haga el "proxy" que redirige la petición al líder de ese momento

LEADER_LIFETIME = 50 # (s) Lifetime in seconds
DEVIATION_RANGE = 20 # (%) Deviation range of the actual leader lifetime (± %)
PRINT_CONSTANT_NODE_ROLE = True # Prints the role of the node on every role check iteration

log.info("Programa iniciado")

NODE_ID = os.environ["ZOO_MY_ID"]
node_hostname = f"{socket.gethostname()}:5000" # Obtenemos el nombre de red del nodo (contenedor)
log.info(f"Nodo {NODE_ID} arrancando")

time.sleep(random.randint(5, 10))
log.info("Intentando conectar...")

# ZooKeeper escucha por defecto en el puerto TCP 2181 para recibir conexiones de sus clientes
# localhost (127.0.0.1) referencia al host del entorno dentro del propio contenedor
zk = KazooClient(hosts="localhost:2181", timeout=5.0)
zk.start(timeout=60)
log.info("Conectado a ZooKeeper")

zk.ensure_path("/eleccion")
znode_path = zk.create("/eleccion/candidato_", value=node_hostname.encode(), ephemeral=True, sequence=True)
log.info(f"Nodo {NODE_ID} registrado: {znode_path}\n")

server = Server(znode_path.split("/")[-1], zk, leader=False)

threading.Thread(target=server.run, daemon=True).start()

while True:
    # Obtiene los nodos y los ordena alfabéticamente (Núm. de ID de menor a mayor)
    children = sorted(zk.get_children("/eleccion"))
    znode_ID = znode_path.split("/")[-1]

    if znode_ID == children[0]:
        log.info(f"Nodo {NODE_ID}: Soy el lider\n")
        
        zk.create("/leader", value=node_hostname.encode(), ephemeral=True)
    
        server.set_leader(leader=True)
        
        # Tiempo aleatorio para autodestrucción
        time.sleep(random.randint(LEADER_LIFETIME * (1 - (DEVIATION_RANGE/100)),
                                  LEADER_LIFETIME * (1 + (DEVIATION_RANGE/100))))

        log.info(f"(!) Autodestruccion del Nodo {NODE_ID} (!)")
        # Termina Python con error (start.sh finalizará el contenedor)
        os._exit(1)

    else:
        if PRINT_CONSTANT_NODE_ROLE:
            log.info(f"Nodo {NODE_ID}: Soy worker\n")
        time.sleep(2)