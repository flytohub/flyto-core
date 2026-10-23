# Flyto2

[English](README.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [简体中文](README.zh-CN.md) · [Español](README.es.md) · [Português (BR)](README.pt-BR.md)

## AIは「完了」と言う。Flyto2は証拠を確認する。

**ブラウザー、API、ワークフロー。さらに外部アダプターを通じて、実際のROS 2ロボットにも接続。**

ページを開く。クリックする。データを集め、APIを呼び、ファイルを保存する。Flyto2はこれらを実行し、各ステップを記録して、能力契約に沿って証拠を確認します。

**Flyto2はソフトウェアです。** ロボットのファームウェアでもモーター制御プログラムでもありません。ROS 2ロボットには、ホスト側の独立したアダプターから接続します。

| | 今できること |
|---|---|
| 🌐 Web | ブラウザー操作、データ抽出、スクリーンショット |
| ⚡ API | リクエスト実行、結果の変換と連携 |
| 🧩 Workflow | ステップを組み合わせた自動処理 |
| 🔌 MCP | AIクライアントに実行ツールを提供 |
| 🤖 ROS 2 | 外部アダプター経由でロボットの標準ソフトウェアに接続 |
| 🦾 Capabilities | 機器の動作・制限・観測を契約として記述 |

**482モジュール、89カテゴリー、41レシピ。** 現在のCoreに含まれる機能です。

## まず1つ動かしてみよう

~~~bash
python -m pip install "flyto-core[browser]"
playwright install chromium
flyto recipe competitor-intel --url https://github.com/pricing
~~~

ブラウザー操作、実行記録、キャプチャー、レポートを確認できます。

~~~bash
flyto recipes
flyto modules
flyto run my-workflow.yaml
~~~

## ロボットとの接続も、ソフトウェアで

~~~text
AI / ユーザー
     |
Flyto2 AI Space  ->  目標・権限
     |
flyto-core       ->  実行・ワークフロー・記録
     |
ROS 2アダプター   ->  ROS 2 / Nav2  ->  TurtleBot3
~~~

実際のTurtleBot3を使った開発が行われています。ただし、最新の構成での実機エンドツーエンド検証は別途必要です。何でも接続するだけで動く、と主張するものではありません。

**機器のソフトウェアスタックごとに、独立したPackを1つ。** Coreにメーカー固有のモーター制御コードは入れません。

## MCPで使う

~~~bash
python -m pip install flyto-core
python -m core.mcp_server
~~~

MCPツールの公開だけで、ロボットの操作権限が付くことはありません。認可と安全確認はホスト側で行います。

## 実行の記録を残す。

**提出された結果は、証拠で確認する。**

Flyto2は処理を実行し、各ステップを記録。提出された証拠を能力契約と照らし合わせてチェックします。

[ドキュメント](https://docs.flyto2.com) · [PyPI](https://pypi.org/project/flyto-core/) · [ライセンス](LICENSE) · [英語版の詳細](README.md)
