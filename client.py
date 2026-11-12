'''
Cliente Calculadora Restful
Este cliente proporciona una interfaz de usuario que permite enviar y recibir peticiones HTTP
con las operaciones asociadas a una calculadora con acumulador remoto
'''
import customtkinter as ctk
import requests

ops = ["std", "sqrt", "mean", "rst", "add", "sub", "mult", "div"]
fn  = ["del", "="]
buttons = [ (ops[0], 1, 0, "σ\nSTD"), (ops[1], 1, 1, "√\nSQRT"), (ops[2], 1, 2, "x̄\nMEAN"), (ops[3], 1, 3, "AC"),
            (7, 2, 0, "7"),  (8, 2, 1, "8"),    (9, 2, 2, "9"),  (ops[4], 2, 3, "+\nADD"),
            (4, 3, 0, "4"),  (5, 3, 1, "5"),    (6, 3, 2, "6"),  (ops[5], 3, 3, "-\nSUB"),
            (1, 4, 0, "1"),  (2, 4, 1, "2"),    (3, 4, 2, "3"),  (ops[6], 4, 3, "×\nMULT"),
            (0, 5, 0, "0"),  (fn[0], 5, 1, "⌫\nDEL"),  (fn[1], 5, 2, "="),  (ops[7], 5, 3, "÷\nDIV")]

operator = None
accumulator = None
accu_lock = False
args = []

client = requests.Session()

# Esta función se llama cada vez que un número es presionado en la interfaz,
# el valor númerico se asigna a la lista de argumentos de la instrucción
def press(value):
    display.insert("end", f" {value}")
    args.append(value)

# Selecciona el operador escogido por el usuario en pantalla e imprime la expresión resultante en la interfaz
def selected_op(op):
    global operator, accu_lock
    operator = op
    # Si hay acumulador efectivo (!= 0) este se añade como primer argumento de la instrucción resultante
    if not accu_lock and accumulator != None and accumulator != 0:
        args.append(accumulator)
        accu_lock = True
    display.delete(0, "end")
    display.insert(0, get_expression())
    # Una vez seleccionada una operación habilitamos los botones númericos
    for key, button in button_dict.items():
        button.configure(state="enabled")

# Prepara y envía  al servidor (mediante calculate()) la instrucción para resetear el acumulador
def reset():
    global operator, args
    display.delete(0, "end")
    operator = "rst"
    args = []
    calculate()

# Elimina el último argumento de la instrucción
def delete():
    if not(len(args) == 0 or (len(args) == 1 and accu_lock)) :
        args.pop()
        display.delete(0, "end")
        display.insert(0, get_expression())

# La función calculate() es la que se encarga de enviar y recibir las peticiones de cálculo al servidor
def calculate():
    global operator, args, accumulator, accu_lock
    response = client.post("http://127.0.0.1:5000/api/v1/calc", json={"op": operator, "args": args})

    orig_req = response.request
    print(f"=============== REQUEST ===============")
    print(orig_req.method, orig_req.url)
    print(orig_req.body)

    ok = response.json()["ok"]
    res = response.json()[f"{"result" if ok else "error"}"]
    if ok: accumulator = res
    display.delete(0, "end")
    display.insert(0, f"{accumulator:.2f}".rstrip("0").rstrip(".") if ok else "")

    print("=============== RESPONSE ===============")
    print(f"STATUS CODE: {response.status_code}")
    print(f"{"" if ok else ""}RES: {response.json()}\n")

    # check_clientID_value()

    add_log(f"POST {response.request.url}")
    add_log(f"Status: {response.status_code}")
    add_log(f"Resultado: {res}\n")

    disable_nums()
    operator = None
    args = []
    accu_lock = False

# Obtiene la expresión resultante optimizada para la pantalla de la interfaz de la calculadora
def get_expression():
    str = f"{operator}"
    if operator != "rst":
        for num in args:
            if num != None and num != 0: 
                str += f" {num:.2f}".rstrip("0").rstrip(".")
    return str

def add_log(message):
    log.configure(state="normal")
    log.insert("end", str(message) + "\n")
    log.see("end")
    log.configure(state="disabled")

def disable_nums():
    for key, button in button_dict.items():
        if key not in (ops or fn):
            button.configure(state="disabled")

# # Verifica si la identificación del cliente en el servidor ha cambiado, solo pregunta al servidor cuando el ID no está definido
# def check_clientID_value():
#     global client_ID_status
#     if client_ID_status == None or client_ID_status == "Unidentified":
#         try:
#             client_ID_status = client.get("http://127.0.0.1:5000/api/v1/whoami", timeout=1).json()["client_ID"]
#             print(f"Changed Client ID value to: {client_ID_status}\n")
#         except Exception : pass

def on_open():
    try:
        response = client.post("http://127.0.0.1:5000/api/v1/reset_metrics", timeout=5)
    except requests.RequestException:
        print("No se pudo notificar la conexión")

def on_close():
    try:
        response = client.post("http://127.0.0.1:5000/api/v1/metrics", timeout=5)
    except requests.RequestException:
        print("No se pudo notificar la desconexión")
    finally:
        client.close()
        window.destroy()

##### User Interface Block #####
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")
window = ctk.CTk()
window.title("Calculadora")
window.geometry("1000x510")
window.resizable(False, False)
display = ctk.CTkEntry(window, width=320, height=70, font=("Arial", 30), justify="right", corner_radius=12)
display.grid(row=0, column=0, columnspan=4, padx=20, pady=(20, 15), sticky="nsew")
log_frame = ctk.CTkFrame(window, fg_color="transparent")
log_frame.grid(row=0,column=4,rowspan=6,padx=(30, 20),pady=20,sticky="nsew")
log_title = ctk.CTkLabel(log_frame,text="Registro de operaciones",font=("Arial", 16, "bold"))
log_title.pack(pady=(0, 10))
log = ctk.CTkTextbox(log_frame,width=600,height=400,font=("Consolas", 13),corner_radius=12,fg_color="#171B26",text_color="#B0FFCF")
log.pack(fill="both", expand=True)
log.configure(state="disabled")
button_dict = {}
for id, row, column, text in buttons:
    if id in ops and id != "rst": command = lambda value=id: selected_op(value)
    elif id == "=": command = calculate
    elif id == "rst": command = reset
    elif id == "del": command = delete
    else: command = lambda value=id: press(value)
    
    if id in ops and id != "rst":
        fg_color = "#2F6B9A"
    elif id == "=":
        fg_color = "#2E8B57"
    elif id == "del" or id == "rst":
        fg_color = "#8B3A3A"
    else:
        fg_color = "#333333"

    button = ctk.CTkButton(window, text=text, width=70, height=65, font=("Arial", 20), 
                           corner_radius=12, fg_color=fg_color, command=command)
    button.grid(row=row, column=column, padx=6, pady=6, sticky="nsew")
    button_dict[id] = button

# Ajuste de cuadrícula
for column in range(3): window.grid_columnconfigure(column, weight=1)
for row in range(1, 6): window.grid_rowconfigure(row, weight=1)
disable_nums() # Deshabilitamos los números inicialmente a la espera de seleccionar una operación
window.protocol("WM_DELETE_WINDOW", on_close)
window.after(300, on_open)
window.mainloop()