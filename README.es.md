# Flyto2

[English](README.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [简体中文](README.zh-CN.md) · [Español](README.es.md) · [Português (BR)](README.pt-BR.md)

**Sí, se conecta a un robot de verdad.**

También abre sitios web, llama APIs, trabaja con archivos y ejecuta los pasos que hay entre una cosa y otra.

## Prueba algo.

Imagina que quieres revisar una página, sacar capturas, recoger datos y guardar un informe:

```bash
pip install "flyto-core[browser]"
playwright install chromium
flyto recipe competitor-intel --url https://github.com/pricing
```

Es un workflow que puedes ejecutar ahora mismo. No necesitas escribir un prompt. Abre el navegador, ejecuta los pasos y guarda los resultados.

¿Quieres curiosear?

```bash
flyto recipes                 # workflows incluidos
flyto modules                 # herramientas disponibles
flyto run your-workflow.yaml  # ejecuta el tuyo
```

El inventario actual de Core incluye **482 módulos registrados** y **41 recetas**. Navegador, APIs, archivos, datos, pruebas y más.

## ¿Y lo del robot?

Ya estamos conectando Flyto2 con un **TurtleBot3 real a través de ROS 2**.

El robot sigue usando ROS 2 / Nav2. Un adaptador independiente habla con él, mientras Flyto2 ejecuta los pasos de software y guarda el registro.

**Sin firmware especial de Flyto2 en el robot. Sin meter controladores de motores dentro de Core.**

Todavía queda la aceptación completa en hardware de la integración actual. No estamos diciendo que cualquier robot funcione con solo instalar el paquete.

## ¿Qué hay en este repositorio?

**flyto-core** es el motor de ejecución Python de Flyto2.

Puedes usarlo desde Python, YAML, una API HTTP local o un cliente de IA mediante MCP:

```bash
pip install flyto-core
python -m core.mcp_server
```

Conectarse por MCP no da permiso automático para mover equipos físicos. Un host de confianza debe autorizar esas acciones.

Cada pila de software de un equipo tiene su propio Pack. Los drivers específicos de cada marca quedan fuera de Core.

## ¿Cómo sabes qué pasó?

Flyto2 registra cada paso. Si algo falla, puedes revisar el historial y recuperar la ejecución desde un checkpoint cuando sea seguro.

Y cuando una herramienta responde «hecho», Core puede comprobar las pruebas presentadas frente al contrato de esa capacidad.

---

[Sitio web](https://flyto2.com) · [Documentación](https://docs.flyto2.com) · [PyPI](https://pypi.org/project/flyto-core/) · [Issues](https://github.com/flytohub/flyto-core/issues) · [Apache-2.0](LICENSE)
