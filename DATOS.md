# Datos recopilados

Todos los archivos de ejecución están dentro de `paper_data`, junto a `simulator.py`. La ruta depende de la carpeta desde la cual se ejecuta esa copia del programa. Los registros usan **UTC**; en Colombia corresponden a cinco horas más que la hora local.

## Estado y diagnósticos

| Archivo | Descripción |
|---|---|
| `paper_state.json` | Capital virtual inicial, saldo, fecha UTC, posiciones ficticias heredadas, últimas velas procesadas y estadísticas virtuales. Se carga al arrancar. |
| `paper_diagnostics.csv` | Resultado del análisis de cada vela válida procesada y su motivo. Se conserva y amplía. |
| `paper_heartbeat.json` | Última comprobación de cotizaciones y su antigüedad. Se reemplaza aproximadamente cada diez segundos. |
| `paper_events.csv` | Aperturas/cierres/rechazos ficticios heredados o de otras versiones. En la V3 instalada puede no existir porque no se abren nuevas posiciones. |

Las columnas de `paper_diagnostics.csv` son:

| Columna | Significado |
|---|---|
| `event_utc` | Momento en que se escribió el diagnóstico. |
| `bar_utc` | Inicio de la vela M1 cerrada que se analiza. |
| `symbol` | Instrumento: Boom 500 Index o Crash 500 Index. |
| `status` | `NO_SIGNAL`, `SIGNAL` o `RESEARCH_ONLY` en una recopilación V3 nueva. Otros estados pueden pertenecer a versiones anteriores. |
| `side` | `BUY`/`SELL` cuando existe una señal; vacío si no corresponde. |
| `reason` | Explicación de ausencia de señal o del modo investigación. |
| `close` | Cierre de la vela M1 analizada. |
| `atr14` | ATR usado para el análisis. |
| `cash_usd` | Saldo virtual local, separado del saldo de MT5. |
| `quote_utc` | Hora del precio observado para ese análisis. |

Una misma señal genera una fila `SIGNAL` y otra `RESEARCH_ONLY`. No deben sumarse como dos señales distintas. `NO_SIGNAL` describe velas analizadas sin señal; los mensajes de consola por datos ausentes no garantizan una fila correspondiente en este CSV.

## Archivos dentro de market_data

| Archivo | Contenido |
|---|---|
| `quote_observations.csv` | Cotizaciones bid/ask observadas, spread, antigüedad y marca de validez. |
| `quote_gaps.csv` | Brechas entre muestras, retrocesos de hora y precios sin actualizar. |
| `boom_500_index_m5.csv` | Velas M5 cerradas de Boom 500. |
| `boom_500_index_h1.csv` | Velas H1 cerradas de Boom 500. |
| `crash_500_index_m5.csv` | Velas M5 cerradas de Crash 500. |
| `crash_500_index_h1.csv` | Velas H1 cerradas de Crash 500. |
| `exit_quality.csv`, `exit_quality_v2.csv` | Calidad de salida de posiciones ficticias heredadas, si se produce un cierre. Pueden no existir. |

Las velas contienen hora UTC, apertura, máximo, mínimo, cierre, volúmenes reportados por MT5, spread y momento de recopilación. Cada treinta segundos aproximadamente, el recolector solicita hasta **500 velas M5** y **300 velas H1**, y añade las posteriores a la última guardada. El análisis de señales usa M1/M5 de MT5; no hay un archivo independiente de velas M1 completas en esta versión.

Las cotizaciones se muestrean durante el sondeo del programa. **No representan un historial completo de ticks del broker.** Una brecha entre observaciones puede deberse a pausas del proceso o de la conexión; no demuestra por sí sola un salto de precio ocurrido entre las muestras.

## Reinicios y recuperación

Se vuelve a leer el estado JSON y la última fecha de cada CSV de velas. Los demás registros se amplían y el resumen consulta los diagnósticos/eventos. No hay aprendizaje automático ni uso de los CSV para recalcular parámetros.

Durante una pausa no se generan observaciones. La descarga de velas recientes al reiniciar puede cubrir parte de ese intervalo, dentro del historial disponible y de los límites solicitados. No recrea todas las señales que habrían aparecido mientras el bot estaba apagado.

La opción `--reset` está bloqueada en V3. Eliminar o sustituir manualmente `paper_data` sí puede perder el historial. No ejecutes dos copias simultáneas contra la misma carpeta de datos.

## Exportar para una revisión

1. Detén el bot con **Ctrl+C** para obtener una copia consistente.
2. Conserva la carpeta original `paper_data`.
3. Crea un ZIP de esa carpeta y comparte la copia para el análisis.

En PowerShell, desde la carpeta del repositorio, puedes crear la copia con:

```powershell
Compress-Archive -LiteralPath .\paper_data -DestinationPath .\paper_data_revision.zip
```

El comando no borra la carpeta original. Si el ZIP ya existe, elige otro nombre para mantener la versión anterior. Los datos y estos ZIP se excluyen del repositorio mediante `.gitignore`; subir el código a GitHub no sincroniza los registros del PC.

## Interpretación de resultados

Los CSV permiten auditar señales y calidad de los datos. Para medir una estrategia, además hay que definir reglas de salida, costes y cómo tratar intervalos sin observaciones, y separar períodos de ajuste y comprobación. Los conteos `BUY`/`SELL` y el saldo virtual intacto de una V3 nueva no son ganancias obtenidas.
