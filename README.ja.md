# Flyto2

[English](README.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [简体中文](README.zh-CN.md) · [Español](README.es.md) · [Português (BR)](README.pt-BR.md)

**そう、実際のロボットにもつながっています。**

もちろんWebサイトの操作、APIの呼び出し、ファイル処理も。必要なステップをまとめて実行するのがFlyto2です。

## とりあえず動かしてみよう

たとえばページを調べて、データとスクリーンショットを集めて、レポートを保存したいなら：

```bash
pip install "flyto-core[browser]"
playwright install chromium
flyto recipe competitor-intel --url https://github.com/pricing
```

これは実際に実行できるワークフロー。AIへのプロンプトは不要です。ブラウザーを開き、処理を進め、結果を保存します。

ほかにも試すなら：

```bash
flyto recipes                 # ワークフロー一覧
flyto modules                 # ツール一覧
flyto run your-workflow.yaml  # 自分のワークフローを実行
```

現在のCoreには**482の登録モジュール**と**41のレシピ**があります。ブラウザー、API、ファイル、データ処理、テストなどに対応しています。

## ロボットの話、もう少し。

Flyto2は外部のROS 2アダプターを通じて、**実機のTurtleBot3**につながっています。

ロボット側はいつものROS 2 / Nav2を使用。アダプターが通信を担当し、Flyto2がソフトウェアの処理と実行記録を扱います。

**専用ファームウェアをロボットに入れる必要はありません。Coreにモータードライバーを詰め込むこともありません。**

最新の統合構成については、実機を使った一連の受け入れ検証がまだ必要です。どんなロボットでもすぐ動く、という意味ではありません。

## このリポジトリは？

**flyto-core** はFlyto2のPython実行エンジンです。

YAML、Python、ローカルHTTP API、MCPから使えます。AIクライアントにつなぐなら：

```bash
pip install flyto-core
python -m core.mcp_server
```

MCP接続だけで実機の操作権限が付くわけではありません。機器への操作は信頼されたホストが認可します。

機器ごとのソフトウェアスタックは独立したPackに分けます。Coreは機種固有のドライバーを抱えません。

## 実行したら、それで終わり？

どのステップを実行したか、Flyto2には記録が残ります。問題が起きたら履歴を確認し、安全に再実行できる範囲でチェックポイントから復帰できます。

ツールが「完了」と返したときも、Coreは能力契約に沿って提出された証拠をチェックできます。

---

[公式サイト](https://flyto2.com) · [ドキュメント](https://docs.flyto2.com) · [PyPI](https://pypi.org/project/flyto-core/) · [Issues](https://github.com/flytohub/flyto-core/issues) · [Apache-2.0](LICENSE)
