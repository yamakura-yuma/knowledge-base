# knowledge-base

調べたことを溜めておく場所。情報は markdown を正本にし、読む用の HTML は生成する。

## いま入っているもの

### AI コーディングツール・ランドスケープ — [`docs/`](./docs/)

エージェント CLI、IDE 統合、クラウドエージェント、モデルゲートウェイ、共通基盤を
**リクエストが通る経路上の位置**で 4 層に分けて並べたもの。69 項目。

- 読む: [`docs/index.html`](./docs/index.html)（自己完結。外部通信もスクリプトも無し）
- 作り: [`docs/index.md`](./docs/index.md)（分類軸・母集団の決め方・ファイルの役割）
- 更新: [`docs/UPDATE_PROMPT.md`](./docs/UPDATE_PROMPT.md)、または `/update-landscape`

```bash
uv run docs/fetch_metrics.py   # GitHub から実測値を取る
uv run docs/build.py           # HTML を生成する
```

星の数・直近リリース・アーカイブ状態は GitHub API の実測値で、
「いまホットか」の判定はすべてその数字から機械的に出している。
裏が取れなかった値は空欄のままにしてあり、推測では埋めていない。
