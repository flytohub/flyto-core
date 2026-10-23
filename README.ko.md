# Flyto Core

[English](README.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [简体中文](README.zh-CN.md) · [Español](README.es.md) · [Português (BR)](README.pt-BR.md)

## AI는 말할 수 있죠. Flyto Core는 실제로 일하게 합니다.

**브라우저에서 API까지. 외부 어댑터를 통해 ROS 2 로봇까지. 하나의 오픈소스 실행 엔진.**

AI가 계획을 세웠어요. 그다음은요?

웹페이지를 열고, 데이터를 가져오고, API를 호출하고, 파일을 만들고, 다음 단계로 넘어가세요. Flyto Core는 이런 작업을 일회성 스크립트가 아니라 재사용할 수 있는 워크플로로 만듭니다.

그리고 화면 안에서만 끝나지 않습니다. **Flyto2는 이미 별도의 어댑터를 통해 ROS 2 로봇과 연결하고 있습니다.** Core는 소프트웨어 실행과 기능 계약을 담당하고, 로봇 제어는 별도의 어댑터와 로봇의 기존 ROS 2 스택이 담당합니다.

> **하나의 Core. 다양한 세상.**
>
> 🌐 브라우저 자동화와 데이터 추출  
> 🔌 API, 파일, MCP, 워크플로  
> 🤖 ROS 2 로봇(외부 어댑터로 연결)  
> 🦾 LeRobot 로봇팔(별도 팩 개발 중)  
> 🏠 스마트 기기(기기 소프트웨어 스택별 독립 팩)

**Flyto Core는 로봇도, 모터 제어 프로그램도 아닙니다. 순수 소프트웨어 실행 엔진입니다.**

## 30초 만에 실행하기

~~~bash
python -m pip install "flyto-core[browser]"
playwright install chromium
flyto recipe competitor-intel --url https://github.com/pricing
~~~

각 실행 단계, 브라우저 캡처, 결과 보고서를 확인할 수 있습니다.

~~~bash
flyto recipes
flyto modules
flyto run my-workflow.yaml
~~~

현재 Core에는 **482개 모듈, 89개 카테고리, 41개 레시피**가 있습니다. 모든 추가 팩을 설치할 필요는 없습니다.

## 왜 쓸까요?

- **AI의 아이디어를 실제 작업으로.** 브라우저, API, 파일을 하나의 워크플로로.
- **AI 도구와 연결.** MCP 서버와 모듈 레지스트리.
- **외부 장비와 연결.** 승인된 기능 계약과 별도의 장비 팩.
- **실행 내용을 확인.** 추적 기록, 증거, 체크포인트.
- **실패했을 때 무작정 재시도하지 않음.** 안전 규칙에 따라 복구합니다.

### Core는 가볍게, 연결은 자유롭게

**장비 소프트웨어 스택 하나당 별도의 팩 하나.** ROS 2는 로봇 어댑터에, LeRobot은 별도 팩에 둡니다. ESP32나 가전제품도 실제 스택에 맞는 팩으로 연결합니다. 제조사별 모터 제어 코드를 Core에 넣지 않습니다.

ROS 2 연결용 구현이 있다는 것과 최신 통합 구성이 실제 장비에서 끝까지 검증됐다는 것은 다릅니다. LeRobot 로봇팔 팩은 아직 개발 중입니다. 모든 장비가 설치 즉시 동작한다고 주장하지 않습니다.

## MCP로 연결하기

~~~bash
python -m pip install flyto-core
python -m core.mcp_server
~~~

MCP 도구를 사용할 수 있다고 해서 로봇을 움직일 권한까지 자동으로 생기는 것은 아닙니다.

## 실행했다고 끝난 건 아닙니다

AI가 “완료”라고 말해도 실제 결과가 확인된 것은 아닐 수 있습니다. Core는 실행 기록과 계약에 정의된 증거를 다루고, Flyto2 호스트 / AI Space가 권한, 독립적인 관측과 최종 작업 판정을 맡습니다.

**AI가 대답하는 걸 넘어, 직접 일을 하게 만드세요.**

[Full README in English](README.md) · [Documentation](https://docs.flyto2.com) · [PyPI](https://pypi.org/project/flyto-core/) · [Apache-2.0 License](LICENSE)
