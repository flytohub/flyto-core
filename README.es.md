# Flyto2

[English](README.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [简体中文](README.zh-CN.md) · [Español](README.es.md) · [Português (BR)](README.pt-BR.md)

## MENOS CHARLA. MÁS ACCIÓN.

**Navegadores, APIs, workflows y robots ROS 2 reales conectados mediante adaptadores externos.**

La IA puede explicarte lo que hay que hacer. Flyto2 da el siguiente paso: abrir páginas, pulsar botones, extraer datos, llamar APIs, guardar archivos y convertir todo eso en workflows ejecutables.

**Flyto2 es software.** No es un robot, firmware ni un controlador de motores. Para ROS 2 usamos un adaptador independiente y el software que el robot ya tiene: ROS 2 / Nav2.

| | Acciones disponibles |
|---|---|
| 🌐 Web | Automatizar el navegador, extraer información y hacer capturas |
| ⚡ APIs | Encadenar llamadas y procesar resultados |
| 🧩 Workflows | Ejecutar tareas con varios pasos |
| 🔌 MCP | Dar herramientas de ejecución a clientes de IA |
| 🤖 ROS 2 | Conectar robots estándar mediante adaptadores externos |
| 🦾 Capacidades | Describir acciones, límites y observaciones con contratos |

**482 módulos · 89 categorías · 41 recetas listas para ejecutar.** Inventario actual de Core.

## Pruébalo ahora

~~~bash
python -m pip install "flyto-core[browser]"
playwright install chromium
flyto recipe competitor-intel --url https://github.com/pricing
~~~

Verás los pasos ejecutados, capturas y un informe. También puedes explorar:

~~~bash
flyto recipes
flyto modules
flyto run my-workflow.yaml
~~~

## Software conectado con robots de verdad

~~~text
Persona / IA
     |
Flyto2 AI Space  ->  objetivo y permisos
     |
flyto-core       ->  ejecución, workflows, trazas
     |
Adaptador ROS 2  ->  ROS 2 / Nav2  ->  TurtleBot3
~~~

La integración ROS 2 se ha desarrollado con equipos TurtleBot3 reales. La aceptación física completa de la versión integrada todavía requiere pruebas específicas; no prometemos que cualquier robot funcione nada más instalar Core.

**Una pila de software de dispositivo, un pack independiente.** Los controladores y motores de cada marca se quedan fuera de Core.

## MCP para tus agentes

~~~bash
python -m pip install flyto-core
python -m core.mcp_server
~~~

MCP no concede por sí solo permiso para mover una máquina real. La autorización y los límites físicos siguen bajo el control del host.

## La IA dice «listo». Flyto2 mira las pruebas.

**Cada paso deja un registro. Cada resultado tiene evidencia que revisar.**

Flyto2 ejecuta las acciones, guarda lo ocurrido y comprueba la evidencia entregada frente al contrato de capacidades.

[Documentación](https://docs.flyto2.com) · [PyPI](https://pypi.org/project/flyto-core/) · [Licencia](LICENSE) · [README completo en inglés](README.md)
