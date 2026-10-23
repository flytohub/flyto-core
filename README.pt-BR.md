# Flyto2

[English](README.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [简体中文](README.zh-CN.md) · [Español](README.es.md) · [Português (BR)](README.pt-BR.md)

## CHEGA DE PAPO. HORA DE FAZER.

**Navegadores, APIs, workflows e robôs ROS 2 reais conectados por adaptadores externos.**

A IA sabe explicar como fazer. O Flyto2 coloca a execução na jogada: abre páginas, clica, extrai dados, chama APIs, salva arquivos e transforma essas ações em workflows de verdade.

**Flyto2 é software.** Não é um robô, firmware nem um controlador de motores. A integração com ROS 2 usa um adaptador separado e o próprio software ROS 2 / Nav2 do robô.

| | O que dá para fazer |
|---|---|
| 🌐 Web | Automatizar navegador, extrair dados, tirar screenshots |
| ⚡ APIs | Encadear chamadas e processar respostas |
| 🧩 Workflows | Executar tarefas com várias etapas |
| 🔌 MCP | Dar ferramentas reais aos agentes de IA |
| 🤖 ROS 2 | Conectar robôs padrão por adaptadores externos |
| 🦾 Capacidades | Declarar ações, limites e observações por contratos |

**482 módulos · 89 categorias · 41 receitas prontas.** Esse é o inventário atual do Core.

## Rode agora

~~~bash
python -m pip install "flyto-core[browser]"
playwright install chromium
flyto recipe competitor-intel --url https://github.com/pricing
~~~

Você acompanha as etapas, as capturas do navegador e o relatório. Explore mais:

~~~bash
flyto recipes
flyto modules
flyto run my-workflow.yaml
~~~

## Software que chega até o robô

~~~text
Pessoa / IA
     |
Flyto2 AI Space  ->  objetivo e permissões
     |
flyto-core       ->  workflows, execução, registros
     |
Adaptador ROS 2  ->  ROS 2 / Nav2  ->  TurtleBot3
~~~

A integração ROS 2 já teve desenvolvimento com equipamentos TurtleBot3 reais. A validação física completa da versão integrada ainda precisa de testes próprios; isso não significa compatibilidade automática com qualquer robô.

**Uma stack de software por dispositivo, um pack separado.** Drivers de fabricantes e controle dos motores ficam fora do Core.

## MCP para agentes

~~~bash
python -m pip install flyto-core
python -m core.mcp_server
~~~

MCP não libera sozinho a movimentação de equipamento físico. Permissões e limites de segurança são responsabilidade do host.

## A IA disse que terminou. O Flyto2 confere as provas.

**Cada etapa fica registrada. Cada resultado tem evidências para conferir.**

O Flyto2 executa as ações, registra o que aconteceu e verifica as evidências entregues conforme o contrato de capacidade.

[Documentação](https://docs.flyto2.com) · [PyPI](https://pypi.org/project/flyto-core/) · [Licença](LICENSE) · [README completo em inglês](README.md)
