---
name: update-landscape
description: docs/ の AI ツール・ランドスケープを実測値で更新する。GitHub から star・push 日時・リリース数・アーカイブ状態を取り直し、registry.yaml の取りこぼしを直して HTML を組み直すとき、ハーネスのパターン・カタログの出典候補を集め直してパターンを抽出するとき、あるいは「ランドスケープを更新して」と言われたときに使う。
---

# ランドスケープを更新する

手順の正本は [`docs/src/landscape/UPDATE_PROMPT.md`](../../../docs/src/landscape/UPDATE_PROMPT.md)。
**まずそれを読むこと。** ここはその入口で、順番と勘どころだけを書いてある。

## 順番

```bash
uv run docs/fetch_metrics.py   # GitHub から実測値を取る。認証は gh に任せる
uv run docs/build.py           # docs/site/ 以下の HTML を組み直す
```

この順番を守る。`build.py` は `docs/src/data/metrics.json` を読むだけで、
自分では取りに行かない。先に `build.py` を流しても前回の数字が出るだけになる。

## 途中で止まる場所

- **「改名 / 移転を検出」** が出たら、`docs/src/landscape/registry.yaml` の当該項目の
  `repo` を直してから `fetch_metrics.py` を流し直す。放っておくと実測値が腐る。
- **「詳細ティアだが本文が無い」** が出たら、自動昇格した項目に
  `docs/src/landscape/tools/<slug>.md` の本文が要る。
  本文を書くまでは既知の警告として残る。
- **`docs/site/` を直接編集しない。** 生成物なので次のビルドで消える。
  **`docs/src/data/metrics.json` を手で編集しない。** 実測値の置き場所であって、意見の置き場所ではない。

パターン・カタログ（話題④）は同じ回の最後に回す。`uv run docs/collect_candidates.py` で
候補を集め直し、上位のうち未抽出のものを `docs/src/patterns/catalog.yaml` に足す
（UPDATE_PROMPT.md の 7）。候補は `registry.yaml` に入れない。`~/dotfiles` は読むだけ。

どのスクリプトも冪等で、実データに差が無ければファイルに触らない。
続けて 2 回流して git の差分が出ないことが、正しく終わった証拠になる。
