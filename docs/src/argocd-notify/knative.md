# ③ Knative Eventing

> ApiServerSource の receive adapter が Application を watch し、ADD / UPDATE / DELETE を CloudEvents にして Broker へ送る。Trigger が属性でふるい分けて、受け手（Knative Service や通常の Service）へ配る。**検知層は停止中の削除を取りこぼすが、配送層は retry・backoff・DLQ・永続化を宣言だけで持てる。** 6 方式の中で配送層が最も強い。

## アーキテクチャ

```diagram
title: Knative Eventing のアーキテクチャ
caption: 検知層（adapter）と配送層（Broker / Trigger）で、状態の持ち方が違う
height: 470
zones:
  - {label: "argocd namespace", kind: platform, box: [10, 30, 230, 150]}
  - {label: "knative-eventing namespace（Platform）", kind: platform, box: [10, 200, 470, 230]}
  - {label: "notify / App の namespace", kind: app, box: [260, 30, 480, 150]}
  - {label: "受け手", kind: ext, box: [760, 30, 230, 400]}
nodes:
  - {id: app, kind: app, label: "Application（CR）", box: [25, 60, 200, 44]}
  - {id: src, kind: crd, label: "ApiServerSource", mono: ["mode: Resource", "serviceAccountName"], box: [275, 60, 220, 66]}
  - {id: ad, label: "receive adapter", lines: ["Deployment 1 レプリカ"], mono: ["reflector・状態は持たない"], box: [510, 60, 215, 70]}
  - {id: ctl, label: "eventing-controller", mono: ["adapter を作る", "SubjectAccessReview で権限確認"], box: [25, 230, 215, 70]}
  - {id: ing, label: "broker-ingress", mono: ["水平スケール可"], box: [255, 230, 210, 54]}
  - {id: ch, kind: state, label: "Broker / Channel の実装", lines: ["InMemory: 永続化なし"], mono: ["Kafka / RabbitMQ / NATS"], box: [255, 305, 210, 70]}
  - {id: flt, label: "broker-filter", mono: ["Trigger の filter と delivery"], box: [25, 330, 215, 54]}
  - {id: rcv, kind: ext, label: "受け手 Service", mono: ["空の 2xx を返す"], box: [775, 60, 200, 54]}
  - {id: dlq, kind: ext, label: "deadLetterSink", mono: ["knativeerror* 属性付き"], box: [775, 330, 200, 54]}
edges:
  - {from: ad, to: app, kind: watch, via: [[510, 140], [240, 140], [125, 104]], label: watch, dx: -60}
  - {from: ctl, to: ad, kind: http, via: [[600, 265]], label: "Deployment を作る", dx: -110, dy: -6}
  - {from: ad, to: ing, kind: ce, via: [[560, 200], [360, 200]], label: CloudEvent, dx: 30}
  - {from: ing, to: ch, kind: ce}
  - {from: ch, to: flt, kind: ce}
  - {from: flt, to: rcv, kind: ce, via: [[745, 395], [745, 87]], label: "retry・backoff"}
  - {from: flt, to: dlq, kind: ce, via: [[240, 410], [745, 410], [745, 357]], label: "上限超過"}
```

- **検知層（adapter）は状態を持たない。** adapter は informer の store を自前の delegate で実装していて、`Replace` と `Resync` が何もしない（[pkg/adapter/apiserver/delegate.go](https://github.com/knative/eventing/blob/knative-v1.23.0/pkg/adapter/apiserver/delegate.go)）。起動時の初期 list で得たオブジェクトはすべて add イベントとして送る。しかし、前回の状態と突き合わせて「その間に消えたもの」を出す仕組みは無い。
- **resync は 10 時間に 1 回**（同ディレクトリ `adapter.go` の `resyncPeriod := 10 * time.Hour`）。
- **adapter は 1 レプリカ固定。** `MakeReceiveAdapter` が `replicas := int32(1)` で Deployment を作る（[receive_adapter.go](https://github.com/knative/eventing/blob/knative-v1.23.0/pkg/reconciler/apiserversource/resources/receive_adapter.go)）。
  - adapter の共通基盤は `WithHAEnabled` でリーダー選出に入れる。ただし `apiserver_receive_adapter` の `main.go` はこれを呼んでいない（呼んでいるのは mtping）。
- **配送層は状態を持てる。** InMemoryChannel は README に "No Persistence" とあり、ベストエフォート。永続化できる実装は、Kafka Broker・RabbitMQ Broker・NATS JetStream Channel の 3 つがある。それぞれが何を保証するかは、[概要ページの「Broker は必須か」](index.html#broker)で比べた。

## 権限分離

```diagram
title: Knative の権限分離
caption: Platform が CRD・コントローラと Application を見る権限を持ち、App は自分の namespace で Broker / Trigger / 受け手を持つ
height: 430
zones:
  - {label: "Platform 側", kind: platform, box: [10, 30, 480, 360]}
  - {label: "App 側（team-a namespace）", kind: app, box: [510, 30, 480, 360]}
nodes:
  - {id: inst, kind: crd, label: "Knative Eventing のインストール", mono: ["CRD・eventing-controller・broker-*", "ClusterRole: knative-*-namespaced-admin"], box: [25, 60, 450, 70]}
  - {id: src, kind: crd, label: "ApiServerSource（notify namespace）", mono: ["Platform が作る"], box: [25, 155, 450, 54]}
  - {id: rb, kind: crd, label: "RoleBinding in argocd", mono: ["applications: get/list/watch", "→ adapter の ServiceAccount"], box: [25, 235, 450, 70]}
  - {id: pbrk, label: "Platform の Broker", mono: ["EventPolicy で送り手を制限（要 OIDC）"], box: [25, 320, 450, 54]}
  - {id: tb, label: "team-a の Broker / Trigger", mono: ["knative-eventing-namespaced-admin"], box: [525, 60, 450, 54]}
  - {id: svc, label: "受け手 Service と Secret", mono: ["送信先の資格情報は App が持つ"], box: [525, 140, 450, 54]}
  - {id: tsrc, kind: bad, label: "team-a が作る ApiServerSource", mono: ["argocd を見る権限が無く Ready=False"], box: [525, 225, 450, 54]}
  - {id: spoof, kind: bad, label: "team-a の Pod から偽の delete を POST", mono: ["EventPolicy なしでは届いた（run9）"], box: [525, 310, 450, 54]}
edges:
  - {from: inst, to: tb, kind: rbac, label: "namespaced-admin"}
  - {from: rb, to: src, kind: rbac}
  - {from: pbrk, to: tb, kind: ce, via: [[500, 347], [500, 87]], label: "Trigger（cross-namespace は alpha）", dx: 0, dy: 110}
  - {from: spoof, to: pbrk, kind: bad}
```

| 誰が | 何をする | 根拠 |
|---|---|---|
| Platform | CRD とコントローラを入れる。namespace 単位の権限は、集約された ClusterRole `knative-eventing-namespaced-admin` などとして配られる | `config/core/roles/clusterrole-namespaced.yaml` |
| Platform | ApiServerSource の ServiceAccount に、`argocd` namespace の applications の `get` / `list` / `watch` を与える。eventing-controller は SubjectAccessReview でこの 3 つを確かめ、足りなければ `SufficientPermissions=False` にする | [apiserversource.go](https://github.com/knative/eventing/blob/knative-v1.23.0/pkg/reconciler/apiserversource/apiserversource.go) の `runAccessCheck` |
| App | 自分の namespace に Broker・Trigger・受け手を作り、送信先の資格情報を持つ | run9 で `can-i` が yes |
| App | Platform の Broker を購読するには、cross-namespace event links（alpha、既定で無効）と `knsubscribe` の権限が要る。無効なら、Platform 側がイベントを App の Broker へ転送する Trigger を持つ | [cross-namespace-event-links.md](https://github.com/knative/docs/blob/main/docs/versioned/eventing/features/cross-namespace-event-links.md) |

**越境（run9 で実測）:**

- `team-a` に `edit` と `knative-*-namespaced-admin` を与えた ServiceAccount で、`argocd` を見る ApiServerSource を作った。作成はできたが、`SufficientPermissions=False`（"cannot get, list, watch resource applications … in Namespace argocd"）で、Ready にならなかった。自分に RoleBinding を足そうにも、`argocd` への `create rolebindings` は no だった。**他チームの Application は覗けない。**
- 一方で、`team-a` の Pod から Platform の Broker の ingress へ、`Ce-Type: dev.knative.apiserver.resource.delete` の**偽のイベントを POST でき、Platform の受け手まで届いた。** 既定では Broker が送り手を検証しないため。EventPolicy で送り手を制限できるが、それには `authentication-oidc` の有効化が前提になる（[authorization.md](https://github.com/knative/docs/blob/main/docs/versioned/eventing/features/authorization.md)）。この対策は実測していない。受け手でも、`Ce-Source` が API server であることなどを検証する。

## 評価

**削除完了の検知: ○。** `dev.knative.apiserver.resource.delete` が、オブジェクトの消滅から 5 ms で届いた（run3）。本文は消える直前の Application で、`deletionTimestamp` と最後に残った finalizer が入っている。デプロイ完了は、更新のたびに `resource.update` が届くだけ（作成 1 回で 14 件）。Synced かつ Healthy かの判定は、受け手が本文を見て行う。Trigger のフィルタは CloudEvents の属性で分けるもので、本文の `status` では絞れない。

**検知層の耐障害性: ×。** adapter を止めている間に消えた Application の delete は、復旧後も届かなかった（run5）。理由は上のとおりで、状態を持たず、初期 list と前回の状態を突き合わせないため。

オブジェクトがまだ残っている間に復旧すれば、その後の DELETE は届く（run4。自前 finalizer が消滅を止めていた）。finalizer 方式（⑤）を併用していれば、adapter が止まっていても、Application は adapter の復旧後まで残る。

**配送層の回復性: ◎。** Broker と Trigger（その下の Subscription）の `delivery` に、`retry`・`backoffPolicy`（linear / exponential）・`backoffDelay`・`deadLetterSink` を書ける（[event-delivery.md](https://github.com/knative/docs/blob/main/docs/versioned/eventing/event-delivery.md)）。

run8 で、宛先を常に 500 にして確かめた。初回のあと retry を 3 回（間隔 0.5 → 1 → 2 秒）行い、最後に DLQ へ送った。DLQ には `Ce-Knativeerrorcode: 500`・`Ce-Knativeerrordest`・`Ce-Knativeerrordata` が付き、`Ce-Id` は初回と同じだった。

Kafka Broker と RabbitMQ Broker は、4 つのパラメータすべてに対応している。RabbitMQ Broker は、delivery spec が無いと最初の失敗で NACK して捨てるので、必ず書く。MTChannelBasedBroker は、下にある Channel しだい。circuit breaker は Knative には無い。受け手の前に service mesh を置いて持たせる。

adapter から Broker への送信は、失敗するとログを出して終わる（`sendCloudEvent`）。**検知層と配送層の境目にも取りこぼしがある。**

**配送保証: ○。** Broker に入ったイベントは、永続化した実装なら at-least-once。Kafka は topic に書き、RabbitMQ は publisher confirm を待ち、NATS JetStream は明示的な ack を待つ（いずれも文献ベース）。retry をまたいでも `Ce-Id` が変わらないので、受け手はこれで重複を除ける。

ただし adapter は、送るたびに新しい UUID を振る（`event.SetID(uuid.New().String())`）。同じ削除を、再起動の前後などで別々に送った場合は、別の ID になる。冪等キーには、本文の Application の `uid` を使う。

順序は実装しだいで、どれも文献ベース。Kafka Broker は `delivery.order: ordered` を指定すればパーティション単位で保つ。RabbitMQ Broker は Trigger の並列度を 1（既定）にすれば保つ。NATS JetStream は、`MsgId` による重複除去が `duplicateWindow` の間だけ効く。

**可用性: ○。** Kafka Broker は、制御面の HA とデータプレーンの水平スケールを謳っている（Kafka Broker の README）。RabbitMQ は quorum queue、NATS JetStream はストリームの replicas で複製できる（文献ベース）。Operator の `spec.high-availability.replicas` で、制御面のレプリカを増やせる（文献ベース）。ただし adapter は 1 レプリカ固定で、検知層は SPOF のまま残る。複数レプリカ構成は実測していない。

**疎結合: ◎。** 送信先を足すときは Trigger を 1 枚足すだけで、送る側には手を入れない。

**スケーラビリティ: ◎。** broker-ingress と broker-filter は、Deployment として水平にスケールできる。ファンアウトは Trigger の数で宣言する。

**可観測性: ◎。** イベントは CloudEvents そのもので、`Ce-Id`・`Ce-Type`・`Ce-Subject` などが付く。`config-observability` に `tracing-protocol`・`tracing-endpoint`・`metrics-protocol` があり、OTLP で出せる（[observability.yaml](https://github.com/knative/eventing/blob/knative-v1.23.0/config/core/configmaps/observability.yaml)）。adapter の送信は otelhttp を通る（delegate.go のコメント）。`traceparent` が受け手まで伝わるかは、トレースを有効にして確かめていない。

**セキュリティ・権限分離: ○。** 分離でき、他チームの Application を覗くこともできない。ただし偽装を防ぐには、EventPolicy と OIDC の設定が要る。

**運用負荷: △。** 入れる部品が多い（eventing-core、Broker の実装、その下の Kafka / RabbitMQ / NATS）。バージョンと Kubernetes の組み合わせにも縛りがある（v1.23.0 は Kubernetes 1.34 以上が必要）。

**レイテンシ: ◎。** オブジェクトの消滅から受け手まで 5 ms（run3）。
