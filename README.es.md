# Flyto2

[English](README.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [简体中文](README.zh-CN.md) · [Español](README.es.md) · [Português (BR)](README.pt-BR.md)

## La IA sabe hablar. Flyto2 la pone a trabajar.

**Del navegador a las APIs. Y mediante adaptadores externos, también a robots ROS 2. Un solo motor de ejecución de código abierto.**

Tu agente tiene un plan. ¿Y ahora qué?

Abre páginas, extrae datos, llama APIs, guarda archivos y sigue con el siguiente paso. Flyto2 convierte esas acciones en flujos reutilizables, sin tener que unir scripts improvisados.

Y no se queda en la pantalla. **Flyto2 ya se conecta con robots ROS 2 mediante adaptadores externos.** Core aporta la ejecución común y los contratos de capacidades; el adaptador independiente habla con el software ROS 2 del robot.

> **Un solo Core. Muchos mundos.**
>
> 🌐 **Web** — navegación automatizada y extracción de datos  
> 🔌 **Software** — APIs, archivos, MCP y workflows  
> 🤖 **Robótica** — ROS 2 a través de adaptadores externos autorizados  
> 🦾 **Brazos robóticos** — integración LeRobot en desarrollo, como pack aparte  
> 🏠 **IoT** — packs independientes según la tecnología de cada equipo

**Flyto2 es software. No es un robot, ni firmware, ni un controlador de motores.**

## Pruébalo en 30 segundos

~~~bash
python -m pip install "flyto-core[browser]"
playwright install chromium
flyto recipe competitor-intel --url https://github.com/pricing
~~~

Verás los pasos ejecutados, capturas del navegador y un informe.

~~~bash
flyto recipes
flyto modules
flyto run my-workflow.yaml
~~~

El inventario actual incluye **482 módulos registrados, 89 categorías y 41 recetas**. No necesitas instalar todas las integraciones para empezar.

## ¿Qué lo hace interesante?

- **Pasar de las ideas a la acción:** workflows para navegador, APIs y archivos.
- **Conectar agentes:** servidor MCP y registro de módulos.
- **Conectar nuevos sistemas:** packs instalables y contratos de capacidades autorizados.
- **Saber qué pasó:** trazas, evidencias y puntos de control.
- **Recuperarse con cuidado:** nada de repetir acciones físicas inciertas a ciegas.

### Core ligero, posibilidades enormes

**Un pack por pila de software del dispositivo.** ROS 2 queda en su adaptador; LeRobot tendrá su propio pack; ESP32 y los dispositivos inteligentes se conectan mediante packs adecuados. El código específico de motores no debe vivir dentro de Core.

Ya existe trabajo de integración real con ROS 2, pero la aceptación completa en hardware de la versión integrada sigue pendiente. El pack LeRobot está en desarrollo. No prometemos compatibilidad universal ni control inmediato de cualquier robot.

## Dale herramientas a tu agente con MCP

~~~bash
python -m pip install flyto-core
python -m core.mcp_server
~~~

Exponer una herramienta por MCP **no autoriza automáticamente movimientos físicos**.

## Ejecutar no es lo mismo que lograr el objetivo

Una respuesta de “listo” no demuestra que algo haya salido bien en el mundo real. Core registra lo ejecutado y puede evaluar la evidencia declarada. El host / AI Space de Flyto2 controla los permisos, las observaciones independientes y el resultado final.

**Haz que tus agentes hagan cosas. Cosas de verdad.**

[README completo en inglés](README.md) · [Documentación](https://docs.flyto2.com) · [PyPI](https://pypi.org/project/flyto-core/) · [Licencia Apache-2.0](LICENSE)
