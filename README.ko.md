# Flyto2

[English](README.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [简体中文](README.zh-CN.md) · [Español](README.es.md) · [Português (BR)](README.pt-BR.md)

## AI는 끝났다고 말합니다. Flyto2는 증거를 확인합니다.

**브라우저, API, 워크플로. 그리고 외부 어댑터를 통해 실제 ROS 2 로봇까지.**

페이지 열기, 클릭, 데이터 추출, API 호출, 파일 저장. Flyto2는 이런 작업을 실행하고 각 단계를 기록하며 기능 계약에 맞춰 증거를 확인합니다.

**Flyto2는 소프트웨어입니다.** 로봇 펌웨어나 모터 제어 프로그램이 아닙니다. ROS 2 로봇은 별도 호스트 어댑터로 연결하고, 로봇은 원래 사용하던 ROS 2 / Nav2를 그대로 사용합니다.

| | 지금 할 수 있는 것 |
|---|---|
| 🌐 웹 | 브라우저 자동화, 데이터 추출, 스크린샷 |
| ⚡ API | 요청 연결 및 데이터 처리 |
| 🧩 워크플로 | 여러 단계를 하나의 자동화로 실행 |
| 🔌 MCP | AI 클라이언트에 실행 도구 제공 |
| 🤖 ROS 2 | 외부 어댑터를 통해 표준 ROS 2 로봇 연결 |
| 🦾 기능 계약 | 장비 동작과 제한, 관측 요구 사항 선언 |

**482개 모듈 · 89개 카테고리 · 41개 레시피.** 현재 Core 코드에 있는 기능입니다.

## 직접 실행해 보세요

~~~bash
python -m pip install "flyto-core[browser]"
playwright install chromium
flyto recipe competitor-intel --url https://github.com/pricing
~~~

브라우저 작업, 실행 단계, 캡처 및 보고서를 확인할 수 있습니다.

~~~bash
flyto recipes
flyto modules
flyto run my-workflow.yaml
~~~

## 로봇에 닿는 소프트웨어

~~~text
사람 / AI
    |
Flyto2 AI Space  ->  목표와 권한
    |
flyto-core       ->  실행, 워크플로, 기록
    |
ROS 2 어댑터     ->  ROS 2 / Nav2  ->  TurtleBot3
~~~

실제 TurtleBot3를 기반으로 통합 개발이 진행됐습니다. 다만 현재 통합 버전의 전체 실기기 검증은 별도로 남아 있습니다. 모든 장비가 설치 즉시 작동한다는 주장은 하지 않습니다.

**장비 소프트웨어 스택 하나에 별도 Pack 하나.** 제조사별 모터 제어 코드는 Core에 넣지 않습니다.

## MCP로 연결하기

~~~bash
python -m pip install flyto-core
python -m core.mcp_server
~~~

MCP 도구 연결만으로 로봇의 물리적 움직임이 승인되지는 않습니다. 실제 권한과 안전 검사는 호스트가 담당합니다.

## 실행한 모든 단계를 기록합니다.

**제출된 결과를 증거로 확인합니다.**

Flyto2는 작업을 실행하고 각 단계를 남깁니다. 제출된 증거는 기능 계약에 따라 확인합니다.

[문서](https://docs.flyto2.com) · [PyPI](https://pypi.org/project/flyto-core/) · [라이선스](LICENSE) · [전체 영어 README](README.md)
