# Flyto2

[English](README.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [简体中文](README.zh-CN.md) · [Español](README.es.md) · [Português (BR)](README.pt-BR.md)

**네, 실제 로봇에도 연결됩니다.**

웹사이트도 열고, API도 호출하고, 파일도 다룹니다. 그 사이에 필요한 작업까지 한 번에 실행하는 소프트웨어가 Flyto2예요.

## 일단 하나 실행해 볼까요?

웹페이지를 확인하고, 데이터와 스크린샷을 모으고, 보고서까지 저장하려면:

```bash
pip install "flyto-core[browser]"
playwright install chromium
flyto recipe competitor-intel --url https://github.com/pricing
```

바로 실행되는 워크플로입니다. AI에게 프롬프트를 먼저 쓸 필요도 없어요. 브라우저가 열리고, 작업이 진행되고, 결과가 저장됩니다.

더 둘러보려면:

```bash
flyto recipes                 # 내장 워크플로 보기
flyto modules                 # 도구 목록
flyto run your-workflow.yaml  # 직접 만든 워크플로 실행
```

현재 Core에는 **482개 등록 모듈**과 **41개 내장 레시피**가 있습니다. 브라우저, API, 파일, 데이터 처리, 테스트 등을 다룰 수 있습니다.

## 로봇 얘기로 돌아가서…

Flyto2는 외부 ROS 2 어댑터를 통해 **실제 TurtleBot3**와 연결되어 있습니다.

로봇은 원래 쓰던 ROS 2 / Nav2를 그대로 사용합니다. 어댑터가 통신을 담당하고, Flyto2는 소프트웨어 작업 실행과 기록을 담당해요.

**로봇에 전용 Flyto2 펌웨어를 설치할 필요도, Core에 모터 드라이버를 넣을 필요도 없습니다.**

최신 통합 버전의 실기기 전체 검증은 아직 남아 있습니다. 어떤 로봇이든 설치만 하면 동작한다는 뜻은 아닙니다.

## 이 저장소는 뭔가요?

**flyto-core**는 Flyto2의 Python 실행 엔진입니다.

YAML 워크플로, Python, 로컬 HTTP API, MCP로 사용할 수 있습니다. AI 클라이언트에 연결하려면:

```bash
pip install flyto-core
python -m core.mcp_server
```

MCP가 연결됐다고 로봇의 움직임이 자동으로 허가되지는 않습니다. 실제 장비 접근은 신뢰된 실행 호스트가 승인해야 합니다.

장비 소프트웨어 스택마다 별도 Pack을 둡니다. 제조사별 드라이버는 Core 밖에 남겨둡니다.

## 실행 뒤에는요?

Flyto2는 각 단계에서 무슨 일이 있었는지 기록합니다. 문제가 생기면 기록을 보고, 안전한 경우 체크포인트부터 다시 실행할 수 있습니다.

도구가 “완료”라고 답해도 Core는 기능 계약에 따라 제출된 증거를 검사할 수 있습니다.

---

[웹사이트](https://flyto2.com) · [문서](https://docs.flyto2.com) · [PyPI](https://pypi.org/project/flyto-core/) · [Issues](https://github.com/flytohub/flyto-core/issues) · [Apache-2.0](LICENSE)
