# Flyto Core

[English](README.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [简体中文](README.zh-CN.md) · [Español](README.es.md) · [Português (BR)](README.pt-BR.md)

## AIは会話できる。Flyto Coreなら、実際に動ける。

**ブラウザーからAPIへ。そして外部アダプター経由でROS 2ロボットまで。ひとつのオープンソース実行エンジン。**

AIがプランを考えた。その次は？

Webページを開く。情報を集める。APIを呼ぶ。ファイルを作る。次のステップへ進む。Flyto Coreなら、これらを使い捨てのスクリプトではなく、再利用できるワークフローにできます。

そして画面の中だけではありません。**Flyto2では、外部アダプターを通じてすでにROS 2ロボットとの接続を進めています。** Coreが担当するのはソフトウェアの実行と能力契約。ロボットの制御は、ロボット側の標準ROS 2スタックと独立したアダプターが担当します。

> **ひとつのCore。いくつもの世界。**
>
> 🌐 ブラウザー操作とデータ収集  
> 🔌 API、ファイル、MCP、ワークフロー  
> 🤖 ROS 2ロボットとの連携（外部アダプター）  
> 🦾 LeRobotアーム連携（独立パックとして開発中）  
> 🏠 スマート機器（それぞれのソフトウェアスタックに合う独立パック）

**Flyto Coreはロボット本体でも、モーター制御ソフトでもありません。ソフトウェア実行エンジンです。**

## まず動かしてみよう

~~~bash
python -m pip install "flyto-core[browser]"
playwright install chromium
flyto recipe competitor-intel --url https://github.com/pricing
~~~

実行ステップ、ブラウザーのキャプチャー、レポートを確認できます。

~~~bash
flyto recipes
flyto modules
flyto run my-workflow.yaml
~~~

現在のCoreには、**482モジュール、89カテゴリー、41のレシピ**があります。追加の連携パックをすべて入れる必要はありません。

## 何がすごいの？

- **アイデアをアクションに。** Web、API、ファイルなどをひとつのワークフローに。
- **AIツールと接続。** MCPサーバーとモジュールレジストリ。
- **別の機器と接続。** ホストで承認された能力契約と外部パック。
- **何が実行されたかわかる。** トレース、証拠、チェックポイント。
- **失敗しても無謀に再実行しない。** 再実行はアクションの安全ルールに従います。

### ソフトウェアは軽く、連携は柔軟に

**機器のソフトウェアスタックごとに、パックはひとつ。** ROS 2はロボット用アダプターに、LeRobotは独立パックに。ESP32や家電も、その機器に合うパックで接続します。機種固有のモーター制御コードをCoreに押し込みません。

すでに存在するROS 2連携コードと、**最新構成の実機エンドツーエンド検証が完了した**という主張は別です。LeRobotアーム用パックも開発中です。どんな機器でも、インストールしただけですぐ動くとは主張しません。

## MCPで使う

~~~bash
python -m pip install flyto-core
python -m core.mcp_server
~~~

MCPでツールを公開できても、それだけで実機の操作権限が付くわけではありません。

## ただ実行するだけじゃない

AIが「完了した」と答えても、現実の結果まで証明されたとは限りません。Coreは実行履歴と契約上の証拠を扱い、Flyto2のホスト／AI Spaceが権限、独立した観測、タスク全体の判定を担当します。

**AIにできることを、会話の外へ。**

[English full README](README.md) · [Documentation](https://docs.flyto2.com) · [PyPI](https://pypi.org/project/flyto-core/) · [Apache-2.0 License](LICENSE)
