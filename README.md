# LeaderCalculator
Esta calculadora pretende mostrar el funcionamiento de un sistema distribuido y su gestión al implementar un sistema de liderazgo automático para coordinar las operaciones, con el fin de dar servicio a una calculadora HTTP.

<!-- # Server Side -->
## Implementación
La arquitectura consta de 6 contenedores: 1 contenedor proxy y 5 contenedores de servicio, entre los que habrá un líder y 4 workers.

Para garantizar un sistema de liderazgo resistente se ha optado por ZooKeeper, que mantiene un árbol de nodos (znodes). Cada servidor actúa como host de ZooKeeper y representa a su vez un znodo dentro de dicho árbol, disponiendo así de un identificador. La política de elección del líder consiste en asignar este cargo al nodo con menor identificador.

Para ello, cada contenedor Docker ejecuta un servicio de ZooKeeper junto con un script de Python que se conecta a él mediante `KazooClient` y crea el znodo correspondiente.

Para la comunicación entre contenedores utilizamos la líbreria Flask la cual permite implementar una API HTTP.

Cuando un contenedor se activa, se inicia por una parte el servidor ZooKeeper y por otra un script `main.py`.

Dentro de `main.py` realizamos las siguientes funciones:
- Conexión al servidor ZooKeeper del propio contenedor.
- Creación del znodo que representa el contenedor dentro del árbol.
- Gestión de la autodestrucción.
- Reasignación de un nuevo líder.
- Inicialización del servidor Flask mediante un segundo hilo, ejecutando `server.py`, que permite atender y delegar peticiones.

En conclusión, un contenedor del sistema (exceptuando el proxy) es en última instancia:
1. Host Zookeeper
2. Cliente Zookeeper (KAZOO)
3. Cliente/Servidor Flask (HTTP)

## Autodestrucción del líder
El líder tendrá un tiempo de vida aleatorio, tras este tiempo el líder se autodestruirá. En el archivo *main.py* encontramos dos parámetros configurables, `LEADER_LIFETIME` y `DEVIATION_RANGE`, que permiten establecer el tiempo de vida base y el margen de variación de dicho tiempo, respectivamente.

Para simular mejor un sistema distribuido y las consecuencias del fallo de un servidor integrante, la autodestrucción no sólo se aplica a nivel de znodo sino que se apaga el contenedor entero. Esto implica que cuando se pierde un contenedor, se pierde un host de ZooKeeper, se pierde el znodo que lo representa y se pierde por consecuencia el servicio que este nodo pudiera dar a la calculadora.

## Proxy
La autodestrucción de los líderes presenta la problemática de que deja al cliente sin una dirección de acceso clara a la que enviar las peticiones. Como el sistema distribuido debe ser completamente transparente para el cliente, este no tiene por qué saber a que dirección enviar las peticiones.

Para solventar este problema, se ha implementado un 6to contenedor que precisamente se encarga de actuar como interconexión entre el cliente y el líder de ese momento. Para ello se ha implementado en Python un script que recibe las peticiones y las reenvía al líder mediante HTTP usando Flask.

Dentro del árbol de nodos encontramos dos znodos troncales, uno es `/eleccion` que actua como un contenedor de los znodos que conforman los 5 servidores y otro es el znodo  `/leader` donde se almacena la dirección del líder actual.

El proxy no participa en la gestión del árbol de znodos que dan servicio y no puede modificarlo, sin embargo puede consultarlo, adoptando un rol de observador (*watcher*).

Cuando un candidato es proclamado líder, este actualiza el znodo `/leader` con su dirección. El proxy, como buen *watcher*, implementa una detección de cambio de líder mediante un *@DataWatch* sobre el znodo `/leader`, cuando este sufre cambios el proxy lee la dirección almacenada en dicho nodo y le redirecciona las peticiones entrantes.

Adicionalmente se ha implementado dentro del proxy el registro de métricas, esto se debe principalmente a dos motivos:
- El cliente no debería asumir el trabajo de recolección de métricas.
- Los servidores pueden no registrar correctamente los datos si se autodestruyen en momentos concretos. Como la autodestrucción se produce aleatoriamente no sería realista registrar las peticiones fallidas antes de apagarse, pues se pierde el realismo de un apagado repentino.

Como todo pasa por el proxy, se considera este el mejor punto desde donde registrar las métricas sobre las peticiones. Cabe mencionar que esto introduce un punto crítico ante fallos, posteriormente se expone en el apartado de **Limitaciones y consideraciones**.

## Logger y Métricas
Para poder realizar un seguimiento de lo que está sucediendo durante todo el proceso, se ha implementado un logger. Debido a que estamos tratando con varios contenedores, si bien existe la opción de tener un log independiente para cada contenedor, se considera que tenerlo todo junto y sintetizado facilita el seguimiento, por ello cada script del servidor tiene su propio logger y escribe sus mensajes en la salida estándar (stdout) del proceso. Usamos la herramienta de logs de Docker para imprimirlos en consola y registrarlos en un archivo. 

Podemos visualizarlo mediante el siguiente comando: 
```docker compose logs -f --tail=0 --no-color | Select-String -CaseSensitive "MAIN|PROXY|CALC|#" | Tee-Object calculadora.log -Append ```

Este comando imprime el log a partir del momento en que se ejecuta (`--tail=0`), filtrando los mensajes del servidor identificados por la etiqueta inicial *[MAIN/PROXY/CALC/#]*, y escribe el registro en un archivo llamado *calculadora.log*. Finalmente encontramos el parámetro `-Append` que permite añadir el registro al archivo existente, si lo hay, en lugar de sobreescribirlo en cada ejecución.

Adicionalmente, mediante el comando `docker compose logs -f`, podemos consultar los mensajes de estado generados por ZooKeeper y Kazoo, que permiten observar el funcionamiento interno del proceso de elección de líder interno de ZooKeeper, así como la gestión de conexiones y reconexiones realizada por Kazoo.

Por defecto, en cada iteración los nodos *worker* comprueban si sigue habiendo líder, esto se imprime de la forma `Nodo n: Soy Worker`. Al ejecutarse cada poco tiempo puede enturbiar la salida, para ello se ha introducido la variable `PRINT_CONSTANT_NODE_ROLE` en la parte superior de *main.py* que permite desactivarlo.

Adicionalmente y con el fin de poder observar como rinde el sistema para cada petición se registra su estado (atendida, fallida), el tiempo desde que llega hasta que se responde y qué líder lo atiende.

Finalmente, a partir de los datos brutos, se sintetiza y se obtiene:
- Tiempo de respuesta
  - Media
  - Mediana
  - Percentil 95
  - Percentil 99 
- Cantidad de peticiones atendidas
- Cantidad de peticiones fallidas
- Cantidad de peticiones totales (recibidas por el proxy)
- Historial de líderes
- Distribución de la cantidad de peticiones atendidas por cada uno de los líderes proclamados hasta el momento

Si bien las métricas se implementan e imprimen en el proxy, la orden de inicialización y reseteo de las mismas las proporciona el propio experimento. Esto introduce una limitación mencionada en el apartado de **Limitaciones y consideraciones**. Las ordenes se implementan mediante los endpoints `/api/v1/metrics` y `/api/v1/reset_metrics` de la API proporcionada por el servidor Flask del proxy.

En el script *client.py* las métricas se reinician al abrirse la ventana de la calculadora y se imprimen al cerrarla. Por otro lado en el caso de *threaded_clients.py* se imprimen al finalizar y se reinician de forma opcional al iniciar el mismo experimento, esto puede configurarse mediante la variable `RESTART_METRICS_ON_EXECUTION` ubicada en la parte superior. Esto puede ser interesante si se quiere tener unas métricas acumulativas realizando el experimento bajo distintas condiciones.

## Server.py y rol líder/worker
El script de server.py usa un servidor Flask para implementar unos endpoints que permiten la comunicación entre los contenedores mediante HTTP.

El líder recibe las peticiones, las asigna aleatoriamente a un nodo *worker* y las devuelve al cliente (pasando por el proxy). En la parte superior del script encontramos el flag `EXCLUDE_LEADER_FROM_WORKING`, este permite decidir si el líder también puede escogerse a si mismo para realizar la operación.

El proxy se comunica con el *leader* mediante el endpoint `/api/v1/calc`, mientras que la comunicación entre *leader* y *worker* se realiza mediante el endpoint `/internal/worker_calc`.

<!-- # Client side -->
## Client.py
El script del cliente permite al usuario probar la calculadora mediante una interfaz desplegada en una ventana flotante.
La ventana cuenta con las operaciones de `add, sub, mult, div, mean, std, sqrt y rst` y un historial de operaciones que muestra de forma reducida la respuesta del servidor tras mandarle una operación. En la consola desde donde ejecutamos el script podemos ver mejor la comunicación entre cliente y servidor.

## Threaded_clients.py
Este script ejecuta el lanzamiento de *N* hilos donde cada hilo representa un cliente, este cliente a su vez se dedica a realizar peticiones al servidor mediante la generación aleatoria de instrucciones.
Esto permite testear a baja escala como gestiona el servidor la atención de múltiples clientes concurrentes.
La duración del experimento y el número de clientes es completamente ajustable desde el propio script.

# Limitaciones y consideraciones
1. El hecho de que sólo se disponga de un contenedor proxy introduce un claro punto crítico ante fallos, esto deriva en los siguientes problemas
- Si el proxy cae, el cliente y el servicio de calculadora queda incomunicado.
- Si el proxy cae, las métricas dejan de registrarse

Esto podría solventarse mediante el añadido de más contenedores proxy, si bien esto podría parecer redundante, la realidad es que sería una forma de asegurar con más garantías que los puntos anteriores no sucedan. Tener varios proxys implicaría a su vez implementar un sistema de memoria compartida tanto para el redireccionamiento como para las métricas por lo que introduce mayor complejidad al sistema.

2. Actualmente las peticiones que se envian durante la transición entre la caída de un líder y el establecimiento de uno nuevo, se pierden. Podría implementarse una cola en el proxy que permita garantizar que todas las peticiones se atienden, si bien esto implicaría que el tiempo de respuesta de algunas peticiones fuera muy alto, se garantizaría el atender a la mayoría de las peticiones que actualmente quedan como fallidas.

3. Para poder imprimir las métricas se necesita conocer cuando se ha terminado el experimento, en threaded_clients.py avisamos al proxy cuando se ha terminado el experimento y en client.py esto se avisa al cerrar la ventana flotante con la interfaz. Sin embargo un cliente real no tendría por qué avisar, esto implicaría introducir mecanismos por parte del servidor para poder llevar a cabo el registro de forma completamente autónoma.

4. A diferencia de prácticas anteriores y como no es el objetivo de la práctica, se ha prescindido de la gestión del acumulador por parte del servidor, de forma que este se almacena en el cliente.

5. La implementación de las peticiones mediante HTTP devuelve un json con un campo asociado llamado ok el cual indica si la operación es correcta o no. Los códigos de HTTP solo se han usado para comunicar desde el líder al proxy que ha habido algún tipo de problema. Podría implementarse un uso más extendido y correcto de los códigos de respuesta HTTP.
   
6. A tener en cuenta: Una vez lanzados los contenedores hay que esperar unos segundos a que terminen de arrancar antes de conectar cualquier cliente, de lo contrario estos responderán con un fallo indicando que no encuentran el servidor.
   
Adicionalmente, cabe destacar la existencia de un posible cuello de botella en la arquitectura del sistema, dado que todas las peticiones destinadas a cualquiera de los cuatro nodos *worker* deben pasar necesariamente por un único proxy y, posteriormente, por un único nodo líder encargado de distribuirlas.

Teniendo en cuenta el bajo coste computacional de las operaciones matemáticas implementadas, es razonable plantear la hipótesis de que, bajo gran carga, el líder pueda alcanzar su capacidad máxima de recepción y delegación de peticiones antes de que los *workers* saturen su capacidad de procesamiento. En consecuencia, el rendimiento global podría quedar limitado por la capacidad del líder, impidiendo aprovechar completamente el paralelismo ofrecido por los cuatro *workers*.


<!-- Cada contenidor representa un servidor
Cada una de les entitats calculadora s'executa sobre un servidor (contenidor)
i cada un d'ells executa una instància de ZooKeeper i un client de Kazoo en Python conectat a la pròpia instància del contenidor -->

<!-- 
El client envia la petició a la direcció de localhost i al port 5000 de l'equip real
El motor de docker estableix un pont entre el port 5000 de l'equip i el port 5000 del contenidor
 -->

