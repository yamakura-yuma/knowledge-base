# 文脈の最適化 — いま使っている 3 つと、その対抗馬

> Headroom・CodeGraph・graphify が実際に何を解いていて、同じ問題に別の答えを出しているものが何か。星の数と直近 push は GitHub API の実測値。

## 問題は「文脈が足りない」ではなく「余計なものが多い」

エージェントがトークンを食う理由は、だいたい次の 3 つに割れる。**この 3 つは別の問題で、効く薬も違う。**
手元の 3 ツールは、たまたま 3 つをきれいに分担している。

<pre><code>                   ┌─────────────────────────────────────────┐
  ① 出力が大きい   │ ツールが返す JSON・ログ・ファイル本文が  │ → 渡す前に<b>小さくする</b>
                   │ そのまま文脈に積まれる                  │    Headroom / LLMLingua
                   └─────────────────────────────────────────┘
                   ┌─────────────────────────────────────────┐
  ② 探索が多い     │ grep → Read → grep → Read … を繰り返し   │ → <b>探索の回数を減らす</b>
                   │ 1 ファイル読むたびに文脈が膨らむ        │    CodeGraph / Serena / ast-grep
                   └─────────────────────────────────────────┘
                   ┌─────────────────────────────────────────┐
  ③ 忘れる         │ セッションを跨ぐと前回の理解が消え、     │ → <b>覚えておく</b>
                   │ 毎回ゼロから調べ直す                    │    graphify / GraphRAG / Mem0
                   └─────────────────────────────────────────┘</code></pre>

①は**帯域**の問題、②は**往復回数**の問題、③は**時間**の問題。
同じ「トークンを減らす」でも、効かせる場所が違うので、1 つ入れれば済むという話にはならない。

---

## ① 渡す前に小さくする

| ツール | star | 直近 push | 状態 | 方式 |
|---|---:|---|---|---|
| **Headroom**（使用中） | {{star:headroom}} | {{push:headroom}} | {{status:headroom}} | プロキシとして割り込み、JSON・ログを構造ごと圧縮。元に戻せる |
| LLMLingua | {{star:llmlingua}} | {{push:llmlingua}} | {{status:llmlingua}} | 小さな言語モデルでプロンプト自体を圧縮。研究発 |

**違いは「戻せるか」。** LLMLingua は不可逆で、消した情報は戻らない。Headroom は圧縮結果に印を残し、
モデルが必要と判断したら元テキストを取り直せる（Compress-Cache-Retrieve）。
エージェントのツール出力という用途では、後から原文が要る場面が現実にあるので、この差は大きい。

なお **Headroom は初期に LLMLingua を組み込んでいたが、のちに外している**。
両者は代替関係にあるというより、Headroom が一度試して捨てた選択肢、という関係にある。

### 気をつける点

Headroom の効きは相手を選ぶ。公式ドキュメント自身が列挙している範囲で、
**コードと RAG 本文は素通し**、散文は圧縮率が落ちて速度もむしろ下がる。
繰り返しの多い JSON とログにはよく効く。**つまり①の薬であって、②③には効かない。**

手元の dotfiles には、日本語の応答そのものを短くする `genshijin-compress` というスキルも入っていた。
Headroom とは層が違うが目的は重なるので、**①の薬を 2 つ飲んでいる状態**だった。
ツール出力の圧縮は Headroom に任せる、と決めて genshijin は外した。

---

## ② 探索の回数を減らす

| ツール | star | 直近 push | 状態 | 索引の持ち方 |
|---|---:|---|---|---|
| **CodeGraph**（使用中） | {{star:codegraph}} | {{push:codegraph}} | {{status:codegraph}} | 事前にグラフ化。呼び出し経路ごと返す。ローカル完結 |
| Serena | {{star:serena}} | {{push:serena}} | {{status:serena}} | LSP を使う。索引を自前で持たず、言語サーバに聞く |
| Claude Context | {{star:claude-context}} | {{push:claude-context}} | {{status:claude-context}} | ベクトル DB に埋め込みを置く |
| ast-grep | {{star:ast-grep}} | {{push:ast-grep}} | {{status:ast-grep}} | 索引を持たない。構文木で検索するだけ |

**この列は「索引をどこに置くか」で分かれている。** CodeGraph は自前のグラフ、Serena は LSP、
Claude Context はベクトル DB、ast-grep はその場で構文解析。
索引を持つほど速いが、**古くなると誤った情報を返す**という共通の弱点を抱える。ast-grep だけがその弱点を持たない。

### すでに Serena が入っている可能性がある

見落としやすい点を一つ。**Headroom の `wrap` は Serena を自動でインストールする**仕様で、
Claude Code についてはユーザースコープ（`~/.claude.json`）に登録される。
つまり Headroom を使っている時点で、CodeGraph と Serena が両方いる構成になり得る。

どちらも②の薬なので、**役割が重なっている**。実際にどちらが呼ばれているかは確認したほうがよい。
外すなら `headroom wrap --code-memory none` で Serena の導入だけ止められる。

---

## ③ 覚えておく

| ツール | star | 直近 push | 状態 | 何を覚えるか |
|---|---:|---|---|---|
| **graphify**（使用中） | — | — | 指標なし | 任意の入力（コード・文書・画像）をグラフ化。GitHub リポジトリを特定できず実測が取れない |
| GraphRAG | {{star:graphrag}} | {{push:graphrag}} | {{status:graphrag}} | 文書からエンティティと関係を抽出してグラフ検索 |
| LightRAG | {{star:lightrag}} | {{push:lightrag}} | {{status:lightrag}} | GraphRAG の構築コストを下げた系統 |
| cognee | {{star:cognee}} | {{push:cognee}} | {{status:cognee}} | グラフとベクトルを併用したエージェント記憶 |
| Mem0 | {{star:mem0}} | {{push:mem0}} | {{status:mem0}} | 会話から事実を抽出して持ち越す |
| Letta (MemGPT) | {{star:letta}} | {{push:letta}} | {{status:letta}} | 文脈window の外へ記憶を退避する発想の源流 |

**graphify だけ実測が取れない。** PyPI の `graphifyy` として配布されているが公開リポジトリを特定できず、
この表で唯一、他と同じ物差しに載っていない。star で比べられないという事実自体を、判断材料として書いておく。

③の中はさらに 2 つに割れる。**コードをグラフにする**もの（graphify、GraphRAG）と、
**会話を覚える**もの（Mem0、Letta、cognee）。前者は静的な構造、後者は時間方向の蓄積を扱う。
手元にあるのは前者だけで、**後者は空いている**。Headroom 自身も memory 機能を持つが、
このホストの設定では `memory_enabled: false` になっている。

---

## 重なりと空白

<pre><code>            ①圧縮          ②索引              ③記憶
          ┌────────┐   ┌─────────────┐   ┌──────────────┐
使用中    │Headroom│   │CodeGraph    │   │graphify      │
          │        │   │+ graphify   │   │              │
          └────────┘   └─────────────┘   └──────────────┘
                            ↑序列で整理済み    ↑静的構造のみ

空いている                                  会話の記憶（Mem0 / Letta 系）
                                            Headroom の memory は無効のまま</code></pre>

**重なりは解消した** — ②の Serena は結局どこにも入っていなかった（`headroom wrap` を使えば
既定で入るが、このホストは `headroom install apply` 経由なので発火しない）。実測のうえで
CodeGraph 一本に決め、①の genshijin-compress も外した。
**空いている** — ③の時間方向。セッションを跨いだ蓄積は、いまどのツールも担当していない。

ただし空白が問題だとは限らない。記憶系は**誤って覚えた事実を持ち越す**という固有のリスクがあり、
入れないという判断は十分あり得る。ここでは「空いている」という事実だけを示す。
