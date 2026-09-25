# 推奨構成の詳細

> 概要ページの結論の中身。構成の各部、デプロイ完了と削除完了の取り方、採らない案、基盤側の負荷、通信規格、運用保守。**できること:** 基盤側の設定を触らずに、デプロイ完了と削除完了を取る。**できないこと:** 受信役が、ある Namespace の生存期間中ずっと止まっていた場合は、その削除を取れない。

### 経路を 1 本にしたい場合

2 経路（主経路と安全網）で送るのは、即時性と確実さの両方が要る場合に限る。どちらか一方でよければ、経路は 1 本にする。経路が 1 本のほうが、重複や取りこぼしの原因を追いやすい。

| 優先すること | 使う経路 | 遅延 | 取りこぼし |
|---|---|---|---|
| 即時性（取りこぼしは許容） | ApiServerSource だけ | 消滅から 5〜10 ms（run13・run15） | 受信役が止まっている間の削除 |
| 確実さ（遅延は許容） | 突き合わせだけ | 最大で周期 1 回分（PingSource の最短は 1 分） | 1 周期のうちに作られて消えた Namespace |
| 両方 | 両方（推奨の既定） | 通常は即時 | 受信役が、その Namespace が生きていた間ずっと止まっていた場合だけ |

### デプロイ完了の取り方 {#deploy}

**第一候補は、Knative で Application を観測する形。** Notifications は、trigger・template・service を `argocd` namespace の `argocd-notifications-cm` に書く。通知を変えるたびに基盤側の設定に手を入れることになるので、第一候補から外した。Argo CD の設定を管理しているチームが通知も持つ場合の代替として残す（[①](notifications.html)）。

| 案 | 重複の除去 | 状態 | 基盤側の設定 |
|---|---|---|---|
| **ApiServerSource で Application を観測（推奨）** | 決定的な id（`<uid>:<revision>:deployed`）で、受け手が消す | 持たない（観測 Service は状態なし） | 触らない |
| Notifications の `on-deployed` を Broker に送る | `oncePer` と annotation で 1 回にする | Application の annotation | `argocd-notifications-cm` を触る |

**観測 Service の判定（`deploy_obs.py`、41 行の試作）:**

- `deletionTimestamp` が無い
- `status.operationState.phase == Succeeded`、かつ `status.health.status == Healthy`
- Notifications カタログの `on-deployed` と同じ時刻の条件（health の `lastTransitionTime` と、operation の `startedAt`・`finishedAt` の比較）
- 満たしたら、`id = <uid>:<operationState.syncResult.revision>:deployed` の CloudEvent を Broker に送る

**Notifications と同じ条件式にして、ずれを確かめた（[run19](report.html#run19)）。** 最初の 0.1.0 のデプロイ完了は、Notifications と観測 Service がどちらも同じ時点で出した（差は 9〜18 ms）。

一方で、ずれも 2 つ見つかった。

- **同じ revision に戻したとき。** 0.2.0 から 0.1.0 に戻すと、Notifications は `oncePer: revision` の記録がすでにあるので送らなかった。観測 Service は、同じ id `<uid>:0.1.0:deployed` で送った。受け手が id で重複を消すと、2 回目の 0.1.0 も消えてしまう。**ロールバックも通知したいなら、id に operation の `startedAt` を足す**（`<uid>:<revision>:<startedAt>:deployed`）。
- **更新が多い。** 1 回の sync で、Application の update が 14 件届いた（[run3](report.html#run3)）。観測 Service は、条件を満たす update のたびに送るので、同じ id が 2〜4 通になった。受け手が id で消す前提なら問題にならない。Broker に流す量を減らしたければ、観測 Service の前に Trigger の filter（`kind: Application`）を置き、EventTransform で id を決めてから通す。

**安全網:** 削除側と同じ PingSource で、観測 Service が毎分 Application を list し、条件を満たすものを同じ id で送る。adapter を止めている間にデプロイした 0.2.0 も、次の周期（6 秒後）に届いた（[run19](report.html#run19)）。状態を持たずに済むのは、id が決定的だから。その代わり、Synced/Healthy のあいだは毎分同じ id が送られるので、受け手の重複除去が前提になる。**削除側と部品は共有できる。** 観測 Service 1 つに、Application の判定と Namespace の突き合わせを両方載せられる（試作は別々に書いた）。

**必要な権限:** applications の get/list/watch だけ（argocd namespace の Role）。Argo CD の RBAC にも、Application の annotation にも触らない。

### Broker の土台と、宛先ごとの Trigger

- **永続化の選択肢:** Kafka Broker、RabbitMQ Broker、NATS JetStream の 3 つ。何が保証されるかは[下の表](#broker)。InMemoryChannel は永続化しないので、本番では使わない。
- **宛先ごとの Trigger は、アプリ側の namespace に置く。** 通知基盤の Broker から、アプリ側の namespace の Broker へ転送する Trigger を基盤側が 1 本置き、アプリ側は自分の Broker に宛先ごとの Trigger を置く。delivery の retry と DLQ はアプリ側が決める。
- **宛先の障害は削除を止めない。** アプリ側の宛先を常に 500 にしても、Namespace の削除はそのまま完了した。アプリ側の Trigger が retry を 3 回行ったあと、DLQ に送った（run16）。

### 設計の原則（デバッグしやすさ）

- **イベントの種類ごとに、経路を 1 本に決める。** デプロイ完了は Notifications、削除完了は ApiServerSource（安全網は例外として足す）。
- **決定的な id を付ける。** 削除は `<uid>:deleted`、デプロイは `<uid>:deployed:<revision>`。再送しても、経路が違っても同じ id になる。run13 では、3 つの経路から同じ id が届いた。
- **観測点を 1 か所にする。** すべてを 1 つの Broker に通すと、「Broker に入ったか」で送り側の問題と配送側の問題を切り分けられる。
- **経路を属性に残す。** 拡張属性（今回は `via`）に、どの経路から来たかを入れる。
- **トレースを付ける。** W3C の `traceparent` を付けると、Broker の前後を 1 本のトレースでつなげられる。

### 「削除完了」を何の消滅で定義するか

| 定義 | 取れる時点 | 注意 |
|---|---|---|
| **Namespace の消滅（推奨）** | Terminating が終わり、中身がすべて消えた時点 | 基盤の Job が消すので、Argo CD の削除方法に左右されない。1 Namespace につき 1 通 |
| Application の消滅 | Argo CD の finalizer がすべて外れた時点 | Namespace を Application のマニフェストに含めていれば、Argo CD は Namespace が消えるまで Application を残した（run17）。`CreateNamespace=true` で作った Namespace は通常 tracking されず、削除されない（[sync-options.md](https://github.com/argoproj/argo-cd/blob/v3.5.3/docs/user-guide/sync-options.md)）。Background や非カスケードの削除では、Application と Namespace の消滅がずれる |

### 複数モジュール（app-of-apps・ApplicationSet・sync wave）

1 回のリリースが複数の Application に分かれると、Application ごとに通知が届く。

| 方法 | 内容 | 注意 |
|---|---|---|
| 親 Application だけに subscribe する | app-of-apps の親だけに `on-deployed` を付ける | Argo CD 1.8 で、Application の health 判定から子 Application の health が外れた。親は、子が Healthy になるのを待たない。待たせるには、`argocd-cm` に Application 用の custom health check を足す（[health.md](https://github.com/argoproj/argo-cd/blob/v3.5.3/docs/operator-manual/health.md)、[#3781](https://github.com/argoproj/argo-cd/issues/3781)） |
| 受け手で集約する | 受け手が、同じリリースの通知を束ねる | リリースを識別するキー（ラベルやリビジョン）が要る |
| Namespace 単位にする（削除） | Namespace ごとに 1 通になるので、1 つの Namespace にある複数の Application がまとまる | Namespace と Application の対応は、ラベルか命名規則で取る |

実測はしていない。

### 採らない案

| 案 | 採らない理由 |
|---|---|
| Namespace に finalizer を付ける | 基盤の Job の `--wait` が通知側を待つことになり、密結合になる。namespaces の update という強い権限も要る |
| 基盤の Job を改修して Broker に送らせる | 基盤の設定に通知の都合を持ち込む。実測では動いた（run14。Terminating で止まると Job が失敗するので、その失敗をアラートにできる） |
| 完了した Job オブジェクトを観測する | Job の命名やラベルという契約と、Job が消滅まで待っていることに依存する。Job は `ttlSecondsAfterFinished` で消えることもある |
| 自前の watch サービス（client-go の informer） | informer のキャッシュはメモリにしかない。再起動すると空から始まり、止まっていた間の削除は届かなかった（run18）。`DeletedFinalStateUnknown` が合成されるのは、同じプロセスの中で再 list したときだけ。取りこぼさないには uid 一覧の永続化が要り、それは突き合わせと同じ処理になる。そのうえで HA・retry・DLQ・ファンアウトも自分で持つことになる |
| Application に finalizer を付ける（⑤） | Application への書き込み権限が要り、止まると全チームの削除が止まる。Namespace を基盤が消す前提なら不要 |

### 基盤側の負荷（kind で数えた実数） {#footprint}

| 構成要素 | CRD | Deployment など | ClusterRole | 1 年のリリース数（マイナー数） |
|---|---:|---:|---:|---|
| Knative Eventing 本体（core） | 17 | 5 | 36 | 16（5） |
| + InMemoryChannel と MT Broker | 1 | 5 | 8 | 同上 |
| Kafka Broker（拡張） | 5 | 4 | 6 | 22（6） |
| + Strimzi（Kafka の operator） | 10 | 1 | 7 | 11（8） |
| RabbitMQ Broker（拡張） | 1 | 2 | 2 | 7（5） |
| + RabbitMQ の cluster-operator と topology-operator、cert-manager | 20 | 5 | 18 | 18・12・19 |
| NATS JetStream（拡張） | 1 | 3 | 6 | 18（5） |
| 推奨構成で足す部品（突き合わせ Service、ApiServerSource、EventTransform） | 0 | 3 | 1 | — |
| 参考: Metacontroller | 3 | 1 | 1 | 21（6） |

Knative と Broker の土台は、今回の前提では導入済みとして扱う。そのうえで推奨構成が足すのは、Deployment 3 つ（突き合わせ Service は約 40 行）と ClusterRole 1 つ（namespaces の get/list/watch）だけ。

### Broker の永続化の選択肢 {#broker}

永続化の選択肢は Kafka だけではない。3 つの実装を、一次情報で比べた。

| 実装 | 何が保証されるか | 根拠 | 成熟度・数字 |
|---|---|---|---|
| **Kafka Broker**（`knative-extensions/eventing-kafka-broker`） | Kafka の topic に書く。replication factor を設定できる。制御面の HA、データプレーンの水平スケール。`delivery.order: ordered` でパーティション単位の順序 | [Kafka Broker のドキュメント](https://github.com/knative/docs/blob/main/docs/versioned/eventing/brokers/broker-types/kafka-broker/README.md) | 201 star、knative-v1.23.1（2026-08-25） |
| **RabbitMQ Broker**（`knative-extensions/eventing-rabbitmq`） | exchange と queue は `Durable: true`、メッセージは `DeliveryMode: Persistent`。ingress は publisher confirm（`PublishWithDeferredConfirm` と `Wait()`）で RabbitMQ の ack を待ち、nack なら 500 を返す。`queueType: quorum` を指定できる。Trigger の既定の並列度は 1 で、順序を保つ。delivery spec が無いと、最初の失敗で NACK して**捨てる** | [RabbitMQ Broker の README](https://github.com/knative-extensions/eventing-rabbitmq/blob/main/docs/broker/README.md)、`pkg/rabbit/queue.go`・`message.go`、`cmd/ingress/main.go` | 100 star、knative-v1.23.0（2026-07-28） |
| **NATS JetStream Channel**（`knative-extensions/eventing-natss`） | stream の storage は既定で File、クラスタなら replicas を指定できる。consumer は `AckExplicitPolicy`。失敗したら `NakWithDelay` で遅らせて再配送する。publish のとき CloudEvent の ID を `MsgId` に入れるので、`duplicateWindow` の間は同じ ID の重複を JetStream が除く | [docs/jetstream.md](https://github.com/knative-extensions/eventing-natss/blob/main/docs/jetstream.md)、`pkg/channel/jetstream/dispatcher/` | 48 star、knative-v1.23.2（2026-09-01）。README に "These components are BETA"。JetStream Broker の文書（at-least-once を謳う）は 2026-09-21 に追加されたばかり |

3 つとも、Trigger の `delivery`（retry・backoff・deadLetterSink）に対応している。どれも実測していない。今回の kind で測ったのは、永続化しない InMemoryChannel だけ。選ぶ基準は、どのメッセージ基盤をすでに運用しているかで決めてよい。

---


---

## 通信規格

**送信は HTTP で、本文は CloudEvents 1.0 にそろえる。** 6 方式のどれでも、送信先から見える形を同じにできる。

| 層 | 規格 | この構成での使い方 |
|---|---|---|
| 転送 | HTTP/1.1 POST（TLS） | 全方式の送信がこれ。gRPC の stream を使うのは ⑥（`rpc Watch` の `ApplicationWatchEvent`）だけ |
| イベントの形 | [CloudEvents 1.0](https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/spec.md)（HTTP binding の binary mode = `Ce-*` ヘッダ、または structured mode = `application/cloudevents+json`） | Knative は binary mode で送る（実測で `Ce-Id` などが付いた）。Notifications の template で structured mode の本文を組めば、Broker に入る（run7）。Metacontroller の hook は `Ce-*` ヘッダを自分で付ける（run10） |
| 冪等キー | CloudEvents の `id`（`source` との組で一意） | Application の `metadata.uid` を使う。Knative の ApiServerSource は送るたびに UUID を振るので、再起動の前後で同じ削除が別の `id` になる（`delegate.go`） |
| 分散トレース | [W3C Trace Context](https://www.w3.org/TR/trace-context/)（`traceparent` / `tracestate`） | Knative の RabbitMQ Broker の ingress は、`traceparent` を読んでメッセージに載せる（`cmd/ingress/main.go`）。Notifications と Argo Events の HTTP trigger は付けなかった（実測） |
| 認証 | 送信先ごとに Bearer / Basic / mTLS。Knative 内部では OIDC（`authentication-oidc`） | 資格情報は、送る部品の Secret に置く |
| 型の定義 | CloudEvents の `type`（例 `com.example.argocd.app.deleted`）と `dataschema` | デプロイ・削除・速報で `type` を分け、受け手が振り分けられるようにする |

**CloudEvents にそろえる利点:**

- Broker を後から挟んでも、送信先の実装を変えずに済む。Knative の Trigger は `type`・`source`・`subject` で振り分けるので、直接送っていた頃と同じ形のまま Broker を通せる。
- 受け手の冪等処理（`id` で重複を除く）の書き方が、全方式で共通になる（[microservices.io: Idempotent Consumer](https://microservices.io/patterns/communication-style/idempotent-consumer.html)）。

---

## 運用保守

基盤チームと利用者（アプリチーム）で、持ち物がはっきり分かれる。

```diagram
title: 運用保守の分担
caption: 推奨構成で、基盤チームと利用者がそれぞれ何を持つか
height: 440
dividers:
  - {line: [500, 40, 500, 400]}
zones:
  - {label: "基盤チームが持つもの", kind: platform, box: [10, 30, 480, 370]}
  - {label: "利用者が持つもの", kind: app, box: [510, 30, 480, 370]}
nodes:
  - {id: p1, label: "Argo CD と Notifications", mono: ["trigger / template の管理、アップグレード"], box: [25, 60, 450, 54]}
  - {id: p2, label: "Metacontroller と finalize hook", mono: ["2 レプリカ + リーダー選出、ClusterRole の絞り込み"], box: [25, 130, 450, 54]}
  - {id: p3, label: "詰まった削除の手当て", mono: ["finalizer を手で外す手順、監視"], box: [25, 200, 450, 54]}
  - {id: p4, kind: crd, label: "Knative と Broker（任意）", mono: ["1 マイナーずつの更新、永続基盤の運用"], box: [25, 270, 450, 54]}
  - {id: p5, kind: state, label: "監視・アラート", mono: ["送信失敗、削除待ちの滞留、DLQ"], box: [25, 335, 450, 54]}
  - {id: u1, label: "受け手（送信先の API）", mono: ["uid で冪等に受ける、2xx を返す"], box: [525, 60, 450, 54]}
  - {id: u2, label: "購読の設定", mono: ["subscribe annotation または Trigger"], box: [525, 130, 450, 54]}
  - {id: u3, label: "送信先の資格情報", mono: ["自分の namespace の Secret、更新"], box: [525, 200, 450, 54]}
  - {id: u4, label: "DLQ に落ちたイベントの処理", mono: ["Broker を使う場合"], box: [525, 270, 450, 54]}
edges:
  - {from: p2, to: u1, kind: ce, label: "通知"}
```

### 基盤チームの運用

| 作業 | 内容 | 頻度・根拠 |
|---|---|---|
| アップグレード | Argo CD（Notifications 同梱）と Metacontroller を追従させる。Knative を入れていれば、**1 マイナーずつ**しか上げられない | Knative の [upgrade-installation.md](https://github.com/knative/docs/blob/main/docs/versioned/install/upgrade/upgrade-installation.md)。Knative v1.23.0 は Kubernetes 1.34 以上を要求した（実測） |
| 可用性の維持 | Metacontroller に `--leader-election` を付け、2 レプリカ以上で動かす。hook の Deployment も 2 レプリカ以上にする。止まると削除が完了しなくなる | run10 |
| 詰まった削除の手当て | 送信先が長く落ちていたり、Metacontroller が失われたりすると、Application が消えない。手順は、Metacontroller の finalizer を手で外して削除を完了させ、通知は別途出すか、送らなかったものとして記録する | Argo CD の [app_deletion.md](https://github.com/argoproj/argo-cd/blob/v3.5.3/docs/user-guide/app_deletion.md) にも、finalizer を外す手順がある |
| 監視 | Notifications の `argocd_notifications_deliveries_total{succeeded="false"}`、Metacontroller のメトリクス、`deletionTimestamp` が付いたまま一定時間残っている Application の数、DLQ の件数 | Notifications の monitoring.md、Metacontroller の `--metrics-address` |
| 権限の管理 | Metacontroller の ClusterRole を、applications と hook に必要な範囲まで絞る。既定は `*` | Metacontroller の `metacontroller-rbac.yaml` |
| 作成時の finalizer の保証（任意） | Metacontroller が止まっている間に作られた Application にも finalizer を付けたいなら、admission（Kyverno など）で足す | 実測していない |

### 利用者の運用

| 作業 | 内容 |
|---|---|
| 受け手を作る | 送信先の API に、CloudEvent を受ける口を作る。`id`（Application の `uid`）で重複を除き、成功したら 2xx を返す。Knative の Broker から受けるなら、本文は空で返す（本文を返すと、Broker が CloudEvent ではないとして 500 扱いにする。実測） |
| 購読する | Notifications なら Application の subscribe annotation（apps-in-any-namespace と self-service を使えば、自分の namespace だけで完結する）。Broker を使うなら、自分の namespace に Trigger を置く |
| 資格情報を更新する | 送信先の資格情報は、自分の namespace の Secret に置いて自分で更新する（Notifications の self-service、または自分の受け手） |
| 失敗を見る | Broker を使う場合は、DLQ に落ちたイベントの再処理。直接送る形なら、基盤チームのアラートを受けて送信先を直す |

**利用者は Application に触る権限も、Argo CD の設定を編集する権限も要らない。** 送信先が落ちたときの影響は、推奨構成（直接送る形）では削除の遅れとして基盤側に出る。Broker を挟めば DLQ として利用者側に出る。どちらで受け止めたいかも、Broker を入れるかどうかの判断材料になる。

---

