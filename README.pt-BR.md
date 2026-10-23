# Flyto2

[English](README.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [简体中文](README.zh-CN.md) · [Español](README.es.md) · [Português (BR)](README.pt-BR.md)

## A IA já sabe conversar. O Flyto2 faz ela agir.

**Do navegador às APIs. E, com adaptadores externos, até robôs ROS 2. Um único motor de execução open source.**

Seu agente montou um plano. E agora?

Abra páginas, extraia dados, chame APIs, salve arquivos e execute o próximo passo. O Flyto2 transforma essas ações em fluxos reutilizáveis, em vez de um monte de scripts improvisados.

E não para na tela. **O Flyto2 já se conecta a robôs ROS 2 por meio de adaptadores externos.** O Core cuida da execução e dos contratos de capacidade; o adaptador separado conversa com a pilha ROS 2 que o robô já usa.

> **Um Core. Muitos mundos.**
>
> 🌐 **Web** — automação do navegador e coleta de dados  
> 🔌 **Software** — APIs, arquivos, MCP e workflows  
> 🤖 **Robótica** — ROS 2 com adaptadores externos autorizados  
> 🦾 **Braços robóticos** — integração com LeRobot em desenvolvimento, em pack separado  
> 🏠 **IoT** — packs independentes para diferentes tecnologias de dispositivos

**Flyto2 é software. Não é um robô, firmware ou controlador de motores.**

## Teste em 30 segundos

~~~bash
python -m pip install "flyto-core[browser]"
playwright install chromium
flyto recipe competitor-intel --url https://github.com/pricing
~~~

Você acompanha cada etapa executada, capturas do navegador e um relatório.

~~~bash
flyto recipes
flyto modules
flyto run my-workflow.yaml
~~~

O inventário atual traz **482 módulos registrados, 89 categorias e 41 receitas**. Não precisa instalar todas as integrações para começar.

## Por que usar?

- **Da ideia à ação:** workflows para navegador, APIs e arquivos.
- **Ferramentas para agentes:** servidor MCP e registro de módulos.
- **Mais equipamentos:** packs instaláveis e contratos de capacidades aprovados pelo host.
- **Visibilidade:** rastros de execução, evidências e checkpoints.
- **Recuperação responsável:** nada de repetir uma ação física incerta sem verificar o que aconteceu.

### Core leve, integrações separadas

**Uma stack de software de dispositivo, um pack independente.** ROS 2 fica no adaptador de robótica; LeRobot tem seu próprio pack; ESP32 e eletrodomésticos usam integrações adequadas à stack de cada um. Código específico de motores não entra no Core.

A conexão com ROS 2 já tem implementação e desenvolvimento com robô real, mas a validação completa da versão integrada em hardware ainda está pendente. O pack LeRobot continua em desenvolvimento. Não prometemos controle imediato de qualquer robô ou geladeira.

## Conecte seu agente com MCP

~~~bash
python -m pip install flyto-core
python -m core.mcp_server
~~~

Disponibilizar uma ferramenta via MCP **não libera automaticamente o controle de equipamentos físicos**.

## Executar é diferente de concluir

Se a IA disse “feito”, isso não prova que o resultado aconteceu no mundo real. O Core registra a execução e avalia evidências declaradas. O host / AI Space do Flyto2 cuida das permissões, observações independentes e da decisão final sobre a tarefa.

**Tire seus agentes da conversa e coloque-os em ação.**

[README completo em inglês](README.md) · [Documentação](https://docs.flyto2.com) · [PyPI](https://pypi.org/project/flyto-core/) · [Licença Apache-2.0](LICENSE)
