# Validación realizada

## Comprobaciones del código

Se verificó el paquete distribuido el 12 de octubre de 2026 con estos resultados:

| Comprobación | Resultado |
|---|---|
| Compilación de sintaxis de todos los archivos Python | Correcta. |
| Resumen inicial y persistencia del estado al consultarlo de nuevo | Correctos. |
| `RESEARCH_ONLY=True` y ausencia de llamadas `order_send`/`order_check` en el motor y recolector | Confirmados. |
| Diagnóstico con conexión y datos recientes simulados | Aceptado. |
| Conexión fallida | Rechazada. |
| Cuenta real, otro broker o moneda distinta a USD | Rechazados antes de consultar mercados. |
| Símbolo inexistente, tick antiguo, velas antiguas o historial insuficiente | Rechazados. |
| Cierre de la conexión después del diagnóstico | Verificado en los casos donde se inició conexión. |
| Instalación del paquete en un sistema distinto a Windows x64 | Bloqueada. |

Las pruebas de datos utilizaron respuestas simuladas para evaluar los bloqueos; no ejecutaron órdenes.

## Comprobación en el PC Windows

La consola compartida durante la instalación confirmó:

- Python 3.12.10 de 64 bits.
- MetaTrader5 5.0.6231 y pandas 2.3.3.
- Instalación de dependencias e importaciones correctas.
- Conexión a Deriv demo en USD.
- Cotizaciones recientes para Boom 500 Index y Crash 500 Index.
- 200 velas M1 y 120 velas M5 válidas en ambos instrumentos.
- Arranque de V3 en modo investigación y registro de señales/situaciones sin señal.

Posteriormente hubo avisos transitorios de precio inválido o antiguo en Crash 500, seguidos de nuevos análisis de velas. Esto debe revisarse al evaluar calidad de los registros; no prueba una causa específica de red o de reloj.

## Alcance de esta validación

Se comprobó instalación, conexión, persistencia básica y funcionamiento del modo investigación. No se realizó una medición de rentabilidad, un entrenamiento automático, una prueba de ejecución de órdenes ni una evaluación prolongada de recuperación ante fallos. El repositorio no incluye datos reales del PC ni resultados financieros inventados.

Para futuras modificaciones, repetir los bloqueos de cuenta/datos y comprobar que el historial existente se conserva. Cualquier evaluación de estrategia debe registrar las reglas utilizadas, los costes asumidos y los períodos separados para ajuste y comprobación.
