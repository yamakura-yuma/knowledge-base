# ④ Argo Events

> resource EventSource が Application を informer で監視し、イベントを EventBus（JetStream など）に書き込む。Sensor がそれを購読し、フィルタを通ったものだけ trigger（HTTP など）で送る。**削除完了は 7 ms で届く。ただし検知層は、停止中に起きた削除を取りこぼす。配送層は、設定しないと at-most-once で動く。**

<p class="eli5">Argo Events は、駅とバスにたとえられます。停留所（EventSource）で変化を拾い、バス（EventBus）に乗せ、終点の係（Sensor）が条件に合うものだけを届けます。バスに乗ったあとは、席（保管）が確保されるので安心です。危ないのは二か所で、停留所の Pod が止まっている間の乗客は乗れません。もう一つは、終点の係が初期設定では一回しか届けようとせず、宛先がエラーを返しても「届けた」と扱うことです。</p>

<!-- archify: argo-events.architecture -->

**図の読み方**

- ① EventSource（基盤側）が変化を拾う。⚠ 停止中の変化は取りこぼす（評価マトリクス「検知層の耐障害性 ×」）
- ② EventBus（基盤側、JetStream）に入ったあとは保管される
- ③ Sensor（利用者側）が条件で絞る。⚠ 既定は at-most-once（評価マトリクス「配送保証 △」）
- ④ 宛先と鍵は利用者側に置く

（色と線の読み方: 橙の破線の枠が基盤側、赤の破線の枠が利用者側。緑の線は主な流れ、赤の線と「⚠」は問題点、紫の破線は鍵などの参照。）




## アーキテクチャ

```diagram
title: Argo Events のアーキテクチャ
caption: EventBus が検知層と配送層の間に入り、そこから先は永続化される
height: 400
zones:
  - {label: "argocd namespace", kind: platform, box: [10, 30, 220, 150]}
  - {label: "argo-events namespace", kind: platform, box: [250, 30, 510, 330]}
  - {label: "外部", kind: ext, box: [780, 30, 210, 330]}
nodes:
  - {id: app, kind: app, label: "Application（CR）", box: [25, 60, 190, 44]}
  - {id: es, label: "EventSource の Pod", lines: ["informer（Add/Update/Delete）"], mono: ["Active-Passive・状態なし"], box: [265, 60, 280, 70]}
  - {id: bus, kind: state, label: "EventBus（JetStream）", lines: ["3 レプリカ・PV 推奨"], mono: ["ここから先は永続化"], box: [265, 170, 280, 70]}
  - {id: sn, label: "Sensor の Pod", lines: ["filter（data / Lua script）"], mono: ["retryStrategy・dlqTrigger"], box: [265, 275, 280, 70]}
  - {id: ctl, label: "controller-manager", mono: ["ES / Sensor / EventBus", "を Deployment にする"], box: [560, 60, 185, 70]}
  - {id: ext, kind: ext, label: "HTTP trigger", box: [795, 275, 180, 44]}
  - {id: dlq, kind: ext, label: "dlqTrigger", box: [795, 170, 180, 44]}
edges:
  - {from: es, to: app, kind: watch, label: watch}
  - {from: es, to: bus, kind: ce, label: "publish"}
  - {from: bus, to: sn, kind: ce, label: "subscribe"}
  - {from: sn, to: ext, kind: http}
  - {from: sn, to: dlq, kind: http, via: [[770, 290], [770, 192]], label: "上限超過", dx: -40}
```

- **検知層（EventSource）は状態を持たない。** informer に `DeleteFunc` を登録しているので DELETE は届く（[pkg/eventsources/sources/resource/start.go](https://github.com/argoproj/argo-events/blob/v1.9.11/pkg/eventsources/sources/resource/start.go)）。ただし、止まっている間に消えたものは復旧後に出てこない（[run4](report.html#run4)・[run5](report.html#run5)）。
- **EventBus から先は永続化される。** 本番では EventBus に PV を付けることが推奨されている（[dr_ha_recommendations.md](https://github.com/argoproj/argo-events/blob/v1.9.11/docs/dr_ha_recommendations.md)）。

## 権限分離

```diagram
title: Argo Events の権限分離
caption: クラスタスコープのインストールでは Platform が controller を持ち、App は自分の namespace で EventBus・EventSource・Sensor を作る
height: 400
zones:
  - {label: "Platform 側", kind: platform, box: [10, 30, 480, 330]}
  - {label: "App 側（team-a namespace）", kind: app, box: [510, 30, 480, 330]}
nodes:
  - {id: inst, kind: crd, label: "Argo Events のインストール", mono: ["CRD・controller-manager", "aggregate-to-edit / admin の ClusterRole"], box: [25, 60, 450, 70]}
  - {id: rb, kind: crd, label: "RoleBinding in argocd", mono: ["applications: list/watch", "→ EventSource の ServiceAccount"], box: [25, 160, 450, 70]}
  - {id: ns, kind: crd, label: "namespaced インストール（任意）", mono: ["--namespaced --managed-namespace"], box: [25, 260, 450, 54]}
  - {id: own, label: "EventBus / EventSource / Sensor", mono: ["edit があれば作れる（run9）"], box: [525, 60, 450, 54]}
  - {id: sec, label: "Sensor が参照する Secret", mono: ["送信先の資格情報は App が持つ"], box: [525, 140, 450, 54]}
  - {id: peek, kind: bad, label: "argocd を見る EventSource", mono: ["watcher SA に list 権限なし"], box: [525, 225, 450, 54]}
edges:
  - {from: inst, to: own, kind: rbac, label: "edit に集約"}
  - {from: rb, to: peek, kind: rbac, label: "Platform が与えない限り不可", dy: 18}
```

| 誰が | 何をする | 根拠 |
|---|---|---|
| Platform | CRD と controller-manager を入れる。インストールに含まれる `argo-events-aggregate-to-edit` などの ClusterRole が、既定の `edit` / `admin` に Argo Events の CR を足す | v1.9.11 の `install.yaml` |
| Platform | resource EventSource の ServiceAccount に、`argocd` namespace の applications の `list` / `watch` を与える | [service-accounts.md](https://github.com/argoproj/argo-events/blob/v1.9.11/docs/service-accounts.md) |
| Platform（任意） | controller を `--namespaced --managed-namespace` で namespace ごとに動かす | [managed-namespace.md](https://github.com/argoproj/argo-events/blob/v1.9.11/docs/managed-namespace.md) |
| App | 自分の namespace に EventBus・EventSource・Sensor を作り、Sensor が参照する Secret に資格情報を持つ | [run9](report.html#run9) で `can-i` が yes |

**越境（[run9](report.html#run9)）:** `team-a` の `edit` だけで、EventBus・EventSource・Sensor は作れた。しかし EventSource の ServiceAccount には `argocd` の applications を `list` する権限が無く（`can-i` は no）、自分で与えることもできない。

EventSource の Pod そのものは、kind のノードで inotify の上限に当たって CrashLoop になった。そのため、「Forbidden で止まる」ところまでは見ていない。権限が無いことは `can-i` で確かめた。

**偽装:** 同じ namespace の EventBus に書き込めるのは、同じ namespace の部品に限られる（EventBus は namespace ごとに作る）。チームごとに EventBus を分ければ、他チームへの偽装の経路は無い。これは文献と構成から読んだもので、実測はしていない。

## 導入・運用の労力

### 基盤側の作業

| 作業 | 頻度 |
|---|---|
| Argo Events 本体（CRD・controller-manager）の導入と追従 | 継続 |
| EventSource の ServiceAccount に、対象の list/watch を与える | 対象を増やすたび |

### 利用者側の作業

| 作業 |
|---|
| 自分の namespace に EventBus・EventSource・Sensor を置く（`atLeastOnce` と `policy.status.allow` を必ず指定） |
| Sensor が参照する Secret と受け手を用意する |

## 評価

**削除完了の検知: ○。** オブジェクトの消滅から 7 ms で DELETE が届いた（[run3](report.html#run3)）。

**デプロイ完了: 重複する。** UPDATE を `status.health.status=Healthy` などのデータフィルタで絞ると、完了時に 4 回届いた。さらに削除開始の直後にも 2〜3 回届いた（[run3](report.html#run3) で 2 回、[run6](report.html#run6) で 3 回）。削除直後の更新では、status がまだ Synced / Healthy のままだから。Lua スクリプトのフィルタで `deletionTimestamp` があるものを除くと、この誤報は止まった（完了時の 4 回は残る）。

**検知層の耐障害性: ×。** EventSource を止めている間に消えた Application の DELETE は、届かなかった（[run4](report.html#run4)・[run5](report.html#run5)）。

**配送層の回復性: ○。** trigger に `retryStrategy`（steps・duration・factor・jitter）を書ける。`atLeastOnce: true` にすれば、上限を超えたとき `dlqTrigger` に回す（[more-about-sensors-and-triggers.md](https://github.com/argoproj/argo-events/blob/v1.9.11/docs/sensors/more-about-sensors-and-triggers.md)）。

[run8](report.html#run8) では、**HTTP trigger は既定で 500 を成功扱いにし、1 回で終わった。** `policy.status.allow: [200, 201, 202]` を足すと、retry を 3 回（間隔 0.6 → 1.2 秒）行ってから `dlqTrigger` に送った。circuit breaker は無いが、`rateLimit` はある。

**配送保証: △。** `atLeastOnce` の既定は false で、コメントには "Trigger execution will use at-most-once semantics" とある（`pkg/apis/events/v1alpha1/sensor_types.go`）。true にすれば at-least-once になる。重複を除く仕組みは Sensor 側に無いので、受け手で Application の `uid` を使って冪等にする。

**可用性: ○。** resource EventSource と Sensor は、`spec.replicas > 1` で Active-Passive になる。リーダー選出は NATS か Kubernetes の Lease で行う（[eventsources/ha.md](https://github.com/argoproj/argo-events/blob/v1.9.11/docs/eventsources/ha.md)、[sensors/ha.md](https://github.com/argoproj/argo-events/blob/v1.9.11/docs/sensors/ha.md)）。複数レプリカでの動きは実測していない。

**疎結合: ○。** EventBus を挟むので、送り手と受け手は分かれている。ただし送信先を足すには Sensor を編集する。

**スケーラビリティ: ○。** Sensor を増やせば、同じ EventBus から別々に購読できる。1 つの Sensor の中の処理は、アクティブな 1 Pod が担う。

**可観測性: △。** Prometheus のメトリクス（`argo_events_events_sent_total`・`argo_events_events_sent_failed_total` など）はある。v1.9.11 の `pkg/` には OpenTelemetry への依存が見当たらない。HTTP trigger の送信に CloudEvents のヘッダは付かなかった（実測）。

**セキュリティ・権限分離: ○。** 分離できる。Application を見る権限は Platform が与える。

**運用負荷: △。** EventBus（JetStream 3 レプリカ・PV）と controller が増える。

**レイテンシ: ◎。** オブジェクトの消滅から 7 ms（[run3](report.html#run3)）。
