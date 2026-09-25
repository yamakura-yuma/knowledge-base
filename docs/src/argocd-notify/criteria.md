# 評価軸と採点基準

> 評価マトリクス（概要ページ）の軸の出典と、◎○△× の基準。方式の選定基準と、既存の推奨・事例の調査結果もここに置く。

```grareco
title: 評価軸：11 の物差しで測る
say:
- どれが良いかは、
- 何で測るかしだい
panels:
- icon: key
  head: 出典のある軸
  lines:
  - ISO/IEC 25010
  - Azure Well-Architected
  - microservices.io
- icon: warn
  head: 耐障害性は 2 つに
  lines:
  - 検知層：止まった間を拾えるか
  - 配送層：retry・DLQ・永続化
- icon: people
  head: 基盤を触るか
  lines:
  - 宛先・条件・本文の 3 ケースで
  - 変更のたびに基盤側の設定を
  - 触る方式は大きな減点
bottom: ◎○△× の基準は軸ごとに書いた
```


## 評価軸

「マイクロサービス適正」を 1 列で済ませず、実在を確かめた 4 つの出典の品質特性に分解した。

| 出典 | 使った項目 |
|---|---|
| [ISO/IEC 25010:2023](https://iso25000.com/index.php/en/iso-25000-standards/iso-25010)（製品品質モデル） | Reliability の Availability・Fault tolerance・Recoverability、Flexibility の Scalability、Maintainability の Modularity・Modifiability、Security、Performance efficiency の Time behaviour |
| [Azure Well-Architected Framework の 5 本の柱](https://learn.microsoft.com/en-us/azure/well-architected/pillars) | Reliability、Security、Operational Excellence（observability を含む）、Performance Efficiency |
| [Azure Architecture Center: Interservice communication](https://learn.microsoft.com/en-us/azure/architecture/microservices/design/interservice-communication) | Retry・Circuit Breaker・Distributed tracing・重複メッセージの扱い（冪等性）・非同期メッセージングの Reduced coupling と Multiple subscribers |
| [microservices.io: Idempotent Consumer](https://microservices.io/patterns/communication-style/idempotent-consumer.html) | at-least-once 配送で重複する前提と、メッセージ ID による重複除去 |

これをもとに 11 の軸を立てた。耐障害性は、検知層と配送層で性質がまったく違うので 2 つに分けた。

| 軸 | 何を見るか | ◎ | ○ | △ | × |
|---|---|---|---|---|---|
| 削除完了の検知 | 止まっていないとき、削除開始と区別して消滅を捉えられるか | 消滅を保証して送る | 消滅を捉える（watch の DELETE） | 途中の段階まで | 削除開始しか取れない |
| 検知層の耐障害性 | 検知する部品が止まっていた間の削除を、復旧後に拾えるか | 拾う（レベルトリガ） | 拾うが条件付き | 一部だけ拾う | 拾えない |
| 配送層の回復性 | 送信の retry・backoff・DLQ・circuit breaker | 全部を宣言で設定できる | retry と DLQ はある | retry だけ | 無い |
| 配送保証 | at-least-once / at-most-once、冪等キー、重複、順序 | at-least-once、重複を除く記録も持つ | at-least-once（重複は受け手で除く） | 設定しだいで at-least-once | at-most-once |
| 可用性 | SPOF の有無、複数レプリカとリーダー選出 | 複数レプリカで SPOF が無い | HA を組めるが設定が要る | 単一レプリカのみ | 止まると削除まで止まる |
| 疎結合・独立デプロイ | 送る側と受ける側を別々に変えられるか、送信先の追加 | 送信先の追加が受け手側の変更だけで済む | 設定 1 か所の変更 | 送る側の設定変更が要る | アプリごとのマニフェスト変更が要る |
| スケーラビリティ | 水平スケール、ファンアウト | データプレーンを水平に増やせ、ファンアウトは宣言 | ファンアウトは宣言、処理は単一 | 送信先ごとに個別送信 | ファンアウトを自前で書く |
| 可観測性 | OTel のトレース・メトリクス、CloudEvents、trace context | OTLP で出し、CloudEvents で運ぶ | 自前で入れれば出せる | Prometheus のメトリクスのみ | ほぼ無い |
| セキュリティ・権限分離 | Platform 側と App 側で権限を分けられるか、テナントを越えられないか、資格情報を置く場所 | 分けられ、越境もできない | 分けられるが設定が要る | 分けにくい、または付与が広い | 越境・偽装を防げない |
| 運用負荷・保守性 | 部品の数、自作コードの量 | 既存の部品だけ | 部品が 1〜2 個増える | 部品が多い、または自作コードがある | 部品が多く、自作もある |
| レイテンシ | 実測の遅れ（削除完了から受け手まで） | 10 ms 未満 | 1 秒未満 | 数秒 | 削除完了を取れない |

---

## 変更時の作業の採点 {#change}

通知を足したり変えたりするときに、基盤側の設定（Argo CD 本体、`argocd-notifications-cm`、Namespace を消す Job）を触るかどうかで採点する。基盤側を触る構成は、大きなマイナスとする。

| 方式 | 宛先の追加 | 条件の変更 | 送信内容の変更 | 採点 |
|---|---|---|---|---|
| **推奨（Knative で観測）** | 通知側 | 通知側 | 通知側 | ◎ |
| ① Notifications | 基盤側（self-service なら通知側） | 基盤側 | 基盤側 | × |
| ② PostSync / PostDelete | 全アプリのマニフェスト | 同左 | 同左 | × |
| ③ Knative ApiServerSource | 通知側 | 通知側 | 通知側 | ◎ |
| ④ Argo Events | 通知側 | 通知側 | 通知側 | ◎ |
| ⑤ finalizer | 通知側（Broker を挟めば） | 基盤側の部品 | 基盤側の部品 | △ |
| ⑥ API stream | 通知側 | 通知側 | 通知側 | ○（自前） |

◎ 3 ケースとも通知側だけ　○ 通知側だが自前のコードを直す　△ 一部が基盤側　× 基盤側かアプリ全部

**Notifications を外したことで変わった評価:** デプロイ完了の第一候補が Notifications から観測に移った。評価マトリクスの「疎結合・独立デプロイ」で、Notifications は △ のままだが、推奨構成の弱点ではなくなった。代わりに、推奨構成は同じ id の重複（1 回のデプロイで 2〜4 通）と、ロールバック時の id の衝突を受け手で扱う必要がある。

## 方式の一覧

<div class="pagegrid">
<a class="pcard" href="notifications.html"><b>① Argo CD Notifications</b><span>trigger の条件式を評価し、service で送る。Argo CD に同梱</span></a>
<a class="pcard" href="hooks.html"><b>② PostSync / PostDelete Job</b><span>application-controller が hook の Job を実行する</span></a>
<a class="pcard" href="knative.html"><b>③ Knative Eventing</b><span>ApiServerSource → Broker / Trigger。CloudEvents で運ぶ</span></a>
<a class="pcard" href="argo-events.html"><b>④ Argo Events</b><span>resource EventSource → EventBus → Sensor</span></a>
<a class="pcard" href="finalizer.html"><b>⑤ finalizer 方式（Metacontroller）</b><span>finalizer を付け、最後の 1 つになったら hook が送る</span></a>
<a class="pcard" href="api-stream.html"><b>⑥ Argo CD API stream</b><span>/api/v1/stream/applications を購読する常駐クライアント</span></a>
</div>

①〜③ は依頼で指定された方式、④〜⑥ はこちらから追加で提案した方式。

### 方式の選定基準

依頼で指定された ①〜③ も含め、すべての候補を同じ 3 つの条件に照らした。数字は、2026-09-25 に GitHub API（`gh api`）で取った値。

1. 削除完了のシグナル（watch の DELETE か、自分の finalizer）を自力で受けられる。admission で受ける DELETE は削除開始の時点なので対象外
2. 直近 180 日以内に push がある
3. クラスタの中で閉じてセルフホストできる

| 候補 | 出どころ | star | 直近 push | 最新リリース | 判定 |
|---|---|---:|---|---|---|
| Argo CD Notifications（Argo CD 本体、エンジンは notifications-engine） | 依頼 | 24,240（engine 335） | 2026-09-25（engine 2026-09-23） | v3.5.3（2026-09-14）。engine はリリースが無く、コミット固定で取り込まれている | 条件 1 を満たさない（削除開始までしか取れない）。それでも、デプロイ完了の検知では最良なので採用（①） |
| PostSync / PostDelete hook（Argo CD 本体） | 依頼 | 24,240 | 2026-09-25 | v3.5.3（2026-09-14） | 条件 1 は一部だけ満たす（PostDelete が捉えるのは、管理リソースが消えた後・CR が消える前）。採用（②） |
| Knative Eventing | 依頼 | 1,554 | 2026-09-21 | knative-v1.23.0（2026-07-28） | 条件 1〜3 をすべて満たす。採用（③） |
| Argo Events | 追加提案 | 2,694 | 2026-09-20 | v1.9.11（2026-07-13） | 条件 1〜3 をすべて満たす。採用（④） |
| Metacontroller | 追加提案 | 1,009 | 2026-08-27 | v4.17.2（2026-08-13） | 条件 1〜3 をすべて満たす。finalize hook で ⑤ を実装する土台として採用 |
| controller-runtime（自作の土台） | 追加提案 | 2,960 | 2026-09-25 | v0.25.1（2026-09-14） | 条件 1〜3 をすべて満たす。⑤ を自作する場合の土台。Metacontroller と比べて得るものが少ない（⑤ のページ） |
| Argo CD API server の stream（Argo CD 本体） | 追加提案 | 24,240 | 2026-09-25 | v3.5.3（2026-09-14） | 条件 1〜3 をすべて満たす。採用（⑥） |
| Kyverno | 追加候補 | 8,178 | 2026-09-25 | v1.19.1（2026-09-10） | 条件 1 を満たさない。⑤ の finalizer を作成時に付ける補助にだけ使える |
| Robusta | 追加候補 | 3,101 | 2026-09-24 | 0.50.0（2026-09-16） | 条件 1 を確認できなかった（kubewatch 経由で任意の CRD を監視できるか、ドキュメントで確かめられなかった） |
| Botkube | 追加候補 | 2,310 | 2024-12-11 | v1.14.0（2024-11-13） | 条件 2 を満たさない |
| Tekton Triggers | 追加候補 | 594 | 2026-09-24 | v0.37.1（2026-09-23） | 条件 1 を満たさない（Kubernetes の watch を自分では持たない） |

依頼の 3 方式のうち、① と ② は条件 1 を満たさない。それでも評価には残した。① はデプロイ完了の検知で最良だった。② は「条件 1 を満たさない理由」自体が、比べるうえで役に立つからだ。

---

### 既存の推奨・事例

一次情報を調べたが、**確立した推奨は見つからなかった。**

- Argo CD の公式ドキュメントにあるのは、`on-deleted` を含むカタログ trigger だけ。削除**完了**を通知する方法は書かれていない。
- Argo CD の issue で見つかったのは、`on-deleted` が送られないという報告（[#18203](https://github.com/argoproj/argo-cd/issues/18203)）。これは利用者の設定ミスだった、とコメントで結論が出ている。削除完了を扱う issue は見つからなかった。
- Knative のドキュメントにも、ApiServerSource の配送保証（at-least-once かどうか）の明記は見つからなかった。

