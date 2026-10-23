# Flyto2

[English](README.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [简体中文](README.zh-CN.md) · [Español](README.es.md) · [Português (BR)](README.pt-BR.md)

**Sim, ele se conecta a um robô de verdade.**

Também abre sites, chama APIs, trabalha com arquivos e executa as etapas no meio do caminho.

## Bora testar?

Quer conferir uma página, salvar screenshots, pegar dados e gerar um relatório?

```bash
pip install "flyto-core[browser]"
playwright install chromium
flyto recipe competitor-intel --url https://github.com/pricing
```

É um workflow que você pode executar agora. Nem precisa escrever um prompt para a IA. Ele abre o navegador, roda as etapas e salva os resultados.

Para explorar mais:

```bash
flyto recipes                 # workflows incluídos
flyto modules                 # ferramentas disponíveis
flyto run your-workflow.yaml  # execute o seu
```

O inventário atual do Core tem **482 módulos registrados** e **41 receitas**. Navegador, APIs, arquivos, dados, testes e bastante coisa.

## E o robô?

Já estamos conectando o Flyto2 a um **TurtleBot3 real usando ROS 2**.

O robô continua com ROS 2 / Nav2. Um adaptador separado conversa com ele. O Flyto2 executa as etapas de software e registra o que aconteceu.

**Nada de firmware especial do Flyto2 no robô. Nada de enfiar driver de motor no Core.**

A validação completa em hardware da integração atual ainda precisa ser concluída. Isso não significa que qualquer robô funcione só de instalar o pacote.

## O que tem neste repositório?

**flyto-core** é o motor de execução Python do Flyto2.

Dá para usar via Python, YAML, API HTTP local ou MCP com um cliente de IA:

```bash
pip install flyto-core
python -m core.mcp_server
```

MCP não dá autorização automática para movimentar equipamentos físicos. Um host confiável precisa aprovar essas ações.

Cada stack de software de dispositivo fica em um Pack separado. Drivers de fabricantes não entram no Core.

## Como saber o que aconteceu?

O Flyto2 registra cada etapa. Se algo falhar, dá para inspecionar o histórico e retomar de um checkpoint quando isso for seguro.

E se uma ferramenta responder «concluído»? O Core pode conferir as evidências apresentadas com o contrato daquela capacidade.

---

[Site](https://flyto2.com) · [Documentação](https://docs.flyto2.com) · [PyPI](https://pypi.org/project/flyto-core/) · [Issues](https://github.com/flytohub/flyto-core/issues) · [Apache-2.0](LICENSE)
