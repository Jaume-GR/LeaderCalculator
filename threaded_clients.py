"""
Experimento Clientes HTTP

Lanza múltiples clientes HTTP.
Genera y envía peticiones HTTP al servidor e
imprime el resultado de cada una
"""
import threading
import requests
import random
import json
import time

operations = ["add", "sub", "div", "mult", "sqrt", "mean", "std", "rst"]

RESTART_METRICS_ON_EXECUTION = True # False allows to keep metrics state between executions

# Parámetros principales
client_qty = 2      # Número de clientes
rate = 2.0          # Peticiones/segundo
exp_duration = 60   # Duración del experimento (s)

# Otros 
lbound = 0          # Límite inferior del PRNG
ubound = 100        # Límite superior del PRNG
max_argn = 5        # Cantidad máxima de números por operación que generará el PRNG
dsize = 2           # Número de decimales mostrados por consola

def run_client(client_id, rate, exp_duration):
    accumulator = 0
    client = requests.Session()

    # Calculamos el tiempo de finalización
    start_time = time.perf_counter()
    final = start_time + exp_duration
    next_time = start_time
    while True:
        # Calculamos el tiempo de espera hasta la siguiente petición
        # siguiendo una tasa dada y una distribución exponencial
        next_time += random.expovariate(rate)
        if next_time >= final : break
        time.sleep(max(0, next_time - time.perf_counter()))
        if time.perf_counter() >= final : break

        # Tomamos una operación al azar de las implementadas
        operation = random.choice(operations)
        # Permitimos la generación de algunas instrucciones incorrectas
        argn = 0 if operation == "rst" else random.randint(1, max_argn if operation not in ["div", "mult", "sqrt"] else 2)
        # Hacemos que algunas instrucciones se generen con números enteros y otros con decimales
        randgen = random.choice([random.randint, random.uniform])
        numbers = []
        if accumulator != None and accumulator != 0 and operation != "rst":
            numbers.append(accumulator)
            argn -= 1
        numbers.extend([round(randgen(lbound, ubound), 3) for _ in range(argn)])
        
        instruction = {"op": operation, "args" : numbers}
        print(f"[PREG Cliente {client_id}]:- {operation} {' '.join(str(x) if isinstance(x, int) else f'{x:.{dsize}f}' for x in numbers)}")

        response = client.post("http://127.0.0.1:5000/api/v1/calc", json={"op": operation, "args": numbers})

        ok = response.json()["ok"]
        res = response.json()[f"{"result" if ok else "error"}"]
        if ok: accumulator = res

        print(f"[RESP Cliente {client_id}]:- " + (
              f"El resultado es {str(res) if isinstance(res, int) else f'{res:.{dsize}f}'}."
              if (ok and operation != "rst") else
              f"Acumulador reseteado [{accumulator}]"
              if ok else res) + "\n")

def main():
    if RESTART_METRICS_ON_EXECUTION:
        client = requests.Session()
        metrics = client.post("http://127.0.0.1:5000/api/v1/reset_metrics")

    threads = []

    for client_id in range(1, client_qty + 1):
        thread = threading.Thread(target=run_client, args=(client_id, rate, exp_duration))
        threads.append(thread)
        thread.start()

    for thread in threads: 
        thread.join()

    print("\nEl test ha finalizado.\n")

    # Avisamos al sistema (proxy) que hemos terminado y que imprima las métricas
    client = requests.Session()
    metrics = client.post("http://127.0.0.1:5000/api/v1/metrics")

if __name__ == "__main__": main()