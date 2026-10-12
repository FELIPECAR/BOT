# TradingCloud Demo

Bot de investigación en Python que obtiene precios de **Boom 500 Index** y **Crash 500 Index** desde **Deriv MetaTrader 5 de escritorio**. Registra señales técnicas y datos de mercado para estudiar la estrategia antes de desarrollar funciones adicionales.

**Estado actual: V3, modo investigación.** El programa no envía órdenes a MT5 y no abre posiciones ficticias nuevas. Una señal `BUY` o `SELL` es un resultado del análisis, no una operación ejecutada. Tampoco existe entrenamiento automático: las reglas permanecen iguales hasta que se modifica el código.

## Requisitos

- Windows x64 y Python de 64 bits, versión 3.10 a 3.14.
- Deriv MT5 de escritorio instalado, abierto y conectado a una cuenta **demo en USD** que ofrezca Boom 500 y Crash 500.
- Internet para instalar dependencias y recibir precios; PC encendido durante la recopilación.

El instalador crea un entorno `.venv` dentro de la carpeta del proyecto e instala `MetaTrader5`, `pandas` y `numpy`. Las credenciales se introducen en MT5; el proyecto no requiere escribir contraseñas en sus archivos.

## Instalación y uso en Windows

1. Descarga el repositorio con **Code → Download ZIP** y extrae todo su contenido en una carpeta nueva, o clónalo con Git.
2. Entra en la carpeta donde aparecen `INSTALAR.cmd` e `INICIAR.cmd`.
3. Ejecuta **INSTALAR.cmd** y espera los mensajes `Dependencias OK` e `INSTALACION TERMINADA`. Si no encuentra Python compatible, instala Python x64 desde su página oficial y repite este paso.
4. Abre Deriv MT5 e inicia sesión en la cuenta demo. Abre los gráficos de ambos instrumentos y deja cargar sus velas M1 y M5.
5. Ejecuta **INICIAR.cmd**. Primero comprueba conexión, cuenta, precios e historial. Si todo es válido, arranca la recopilación.

La consola debe mostrar:

```text
CONEXION Y DATOS OK. Iniciando investigacion de precios y senales.
V3 INVESTIGACION: no se abren posiciones ficticias nuevas...
VELA Boom 500 Index ...: SENAL SELL; solo investigacion, sin nueva posicion
```

Mantén MT5 y la consola abiertos. Para detener el proceso, pulsa **Ctrl+C**. Después, **RESUMEN.cmd** muestra el estado virtual, los conteos de señales y el último diagnóstico por instrumento.

Si una consola se cierra antes de poder leerla, abre `cmd`, entra en la carpeta del repositorio y ejecuta `INICIAR.cmd` desde esa consola. También puedes usar Windows+R con `cmd /k "C:\ruta\trading-cloud-demo\INICIAR.cmd"`, sustituyendo la ruta por la carpeta real.

## Qué hace cada archivo

| Archivo | Función |
|---|---|
| `INSTALAR.cmd` | Busca Python compatible y ejecuta el instalador. |
| `preparar.py` | Crea `.venv`, instala dependencias y comprueba sus importaciones. |
| `INICIAR.cmd` | Ejecuta el diagnóstico y, si pasa, inicia el bot. |
| `comprobar_mt5.py` | Comprueba demo Deriv en USD, cotizaciones, historial y modo investigación. |
| `simulator.py` | Calcula señales, conserva el estado y coordina la recopilación. |
| `market_research.py` | Guarda cotizaciones observadas, velas M5/H1 y registros de calidad. |
| `RESUMEN.cmd` | Consulta el estado y las señales guardadas. |
| `requirements.txt` | Define las dependencias. |

## Cómo calcula las señales

Cada nueva vela cerrada de M1 que tenga datos válidos se procesa una vez por instrumento. El análisis consulta **200 velas M1** y **120 velas M5** de MT5; calcula medias móviles exponenciales y un ATR de 14 períodos.

| Resultado | Condiciones del algoritmo |
|---|---|
| `BUY` | EMA9 por encima de EMA21 en M1, EMA21 creciente, EMA21 por encima de EMA50 en M5 y cierre sobre el máximo de las diez velas M1 anteriores. |
| `SELL` | EMA9 por debajo de EMA21 en M1, EMA21 decreciente, EMA21 por debajo de EMA50 en M5 y cierre bajo el mínimo de las diez velas M1 anteriores. |
| `NO_SIGNAL` | Las condiciones no coinciden o actúa el filtro de volatilidad. |

El filtro descarta una vela cuyo rango supera 2.5 veces el ATR de la vela anterior. Las cotizaciones deben cumplir `ask > bid > 0` y tener una antigüedad entre 0 y 45 segundos. Si faltan precios o velas recientes, se omite el análisis afectado y se informa en consola.

Estas condiciones describen el código actual. Las señales registradas por sí solas no demuestran rentabilidad.

## Dónde guarda los datos y cómo los recupera

La carpeta **`paper_data` se crea junto a `simulator.py`**, dentro de la copia que estás ejecutando. Los datos se guardan durante el funcionamiento; no hay que esperar a cerrar la consola.

| Ruta | Contenido y uso |
|---|---|
| `paper_data/paper_state.json` | Estado virtual y última vela procesada. Se recupera al iniciar y se actualiza al procesar velas o cambios de estado. |
| `paper_data/paper_diagnostics.csv` | Señales y motivos de ausencia de señal. Se agregan filas; `RESUMEN.cmd` lo lee. |
| `paper_data/paper_heartbeat.json` | Último estado de precios/conexión, actualizado aproximadamente cada diez segundos. Se reemplaza, no es un historial. |
| `paper_data/paper_events.csv` | Eventos de posiciones ficticias anteriores, si existen. Puede no existir en una instalación nueva en modo investigación. |
| `paper_data/market_data/` | Cotizaciones muestreadas, velas M5/H1 y controles de calidad. |

Al reiniciar desde **la misma carpeta**, se conserva el estado y se amplían los CSV. El recolector consulta la última vela almacenada de cada archivo para añadir las posteriores sin repetirlas. Las señales nuevas se calculan con datos actuales de MT5; los CSV no entrenan un modelo.

Una copia en otra carpeta tiene un historial separado. Mientras el programa está apagado no observa cotizaciones ni registra señales; al volver puede recuperar velas recientes disponibles en MT5, pero no reconstruye todas las observaciones perdidas.

Consulta [la descripción de los datos](DATOS.md) para conocer archivos, columnas, fechas y exportación.

## Qué significa el capital virtual

El valor inicial de **USD 100** pertenece al registro local del programa y es independiente del saldo de la cuenta MT5. En V3 no se abren posiciones ficticias nuevas. Si se continúa un historial anterior con una posición ficticia abierta, el código puede seguirla hasta su cierre y conservar sus eventos.

El proyecto contiene funciones de cálculo de riesgo virtual, pero no contiene llamadas de envío de órdenes al broker. Cambiar `RESEARCH_ONLY` no convierte esta versión en un ejecutor de operaciones MT5; el diagnóstico de este paquete exige que permanezca en `True`.

## Análisis posterior y aprendizaje

Los datos permiten revisar calidad de precios, frecuencia de señales y qué ocurrió después. Una evaluación de estrategia requiere simular entradas/salidas con costes y comprobar los resultados en períodos distintos a los empleados para seleccionar parámetros.

Este repositorio guarda el código y la documentación. Los registros del PC no se suben automáticamente a GitHub ni se envían automáticamente a un asistente. Para una revisión, detén el bot y comparte manualmente una copia comprimida de `paper_data`. El proyecto no incluye un módulo de entrenamiento ni cambios automáticos de reglas.

## Solución de problemas

| Mensaje | Paso a realizar |
|---|---|
| Python no encontrado o incompatible | Instalar Python x64 con pip y volver a ejecutar `INSTALAR.cmd`. |
| Conexión MT5 fallida | Abrir MT5, comprobar el servidor y conectar la cuenta demo. |
| Cuenta DEMO / cuenta no identificada como Deriv | Seleccionar la demo correspondiente dentro de MT5. |
| Instrumento inexistente | Elegir una demo que ofrezca los dos instrumentos indicados. |
| Historial incompleto | Abrir M1 y M5 del instrumento y dejar cargar el historial. |
| Precio o vela desactualizados | Revisar la conexión y la sincronización de fecha/hora de Windows. |

## Validación y mantenimiento

La instalación y la lectura de precios de ambos instrumentos fueron verificadas en Windows el 12 de octubre de 2026. Se comprobaron también sintaxis Python, recuperación de estado y bloqueos de cuenta/datos mediante pruebas locales. Esto no constituye una evaluación de rendimiento de la estrategia. El detalle está en [VALIDACION.md](VALIDACION.md).

`.gitignore` excluye el entorno Python, los registros locales y archivos habituales de credenciales. `.gitattributes` conserva los finales de línea adecuados para los lanzadores Windows. Las actualizaciones de código deben conservar `paper_data` y mantener el modo investigación hasta definir y validar el siguiente alcance.

## Referencias oficiales

- [Python para Windows](https://www.python.org/downloads/windows/)
- [Deriv MT5 de escritorio](https://deriv.com/trading-platforms/mt5/download)
- [Integración Python con MT5](https://www.mql5.com/en/docs/python_metatrader5)
- [Distribución MetaTrader5 en PyPI](https://pypi.org/project/metatrader5/)
- [Pruebas de estrategias y validación en otro período](https://www.metatrader5.com/en/terminal/help/algotrading/testing)
