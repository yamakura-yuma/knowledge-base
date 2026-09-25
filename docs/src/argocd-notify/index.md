# Argo CD Application の完了通知

> Argo CD の `Application` について、デプロイ完了（Synced かつ Healthy）と削除完了（finalizer の処理が終わってオブジェクトと管理リソースが実際に消えた時点）を検知し、外部へ送る 6 つの方式を比べる。根拠は kind 上の Argo CD v3.5.3 での実測と、各プロジェクトのソース・公式ドキュメント。方式ごとの詳細は各ページに分けた。

## 結論

**前提:** Knative Eventing を導入する。Namespace は基盤側の Job が消す。基盤側の設定（Argo CD 本体、`argocd-notifications-cm`、Namespace を消す Job）は、通知を足したり変えたりするときに触らない。

**推奨: 基盤側の設定に手を入れず、Knative で外から観測する。入口は Broker 1 つ。**

| 何を | どう取るか | CloudEvents の id |
|---|---|---|
| デプロイ完了 | ApiServerSource で Application を watch し、観測 Service が「Synced かつ Healthy で、operation が Succeeded」を判定して送る。条件は Notifications の `on-deployed` と同じ式 | `<uid>:<revision>:deployed` |
| 削除完了 | ApiServerSource でラベル付きの Namespace を watch する。DELETE（完全に消えた時点）を EventTransform で変換する | `<Namespace の uid>:deleted` |
| 安全網（両方） | PingSource が毎分、観測 Service に突き合わせをさせる。止まっていた間の変化を拾い、同じ id で送る | 同上 |
| 配送 | 宛先ごとの Trigger・retry・DLQ はアプリ側の namespace に置く。受け手は id で重複を消す | — |

**選んだ理由:**

1. 通知の追加・変更がすべて通知側（obs とアプリの namespace）で済み、基盤側の設定を一度も触らない（[採点表](criteria.html#change)）。
2. 必要な権限は、applications と namespaces の get/list/watch だけ。Application の annotation も、Argo CD の RBAC も使わない。
3. 削除は Namespace が完全に消えた時点で取れる。watch の取りこぼしは突き合わせが拾う（[報告書 run15](report.html#run15)）。
4. 同じ変化が複数の経路から届いても、決定的な id で受け手が 1 通にできる（[報告書 run13・run19](report.html#run19)）。

詳しい構成、実装仕様、採らない案は [推奨構成の詳細](recommended.html) に書いた。

---

## 全体の比較

### 評価マトリクス

<div class="tblwrap">
<table class="mx">
<thead><tr><th>方式</th><th>削除完了の検知</th><th>検知層の耐障害性</th><th>配送層の回復性</th><th>配送保証</th><th>可用性</th><th>疎結合・独立デプロイ</th><th>スケーラビリティ</th><th>可観測性</th><th>セキュリティ・権限分離</th><th>運用負荷</th><th>レイテンシ</th></tr></thead>
<tbody>
<tr><td><a href="notifications.html">① Notifications</a></td><td>× 削除開始</td><td>○ デプロイは拾う / 削除は×</td><td>△ 4 回試行で終わり</td><td>○ oncePer で重複除去</td><td>△ 1 レプリカ</td><td>△ cm の編集</td><td>△ 送信先ごと</td><td>△ Prometheus</td><td>○ self-service</td><td>◎ 同梱</td><td>× 削除完了なし</td></tr>
<tr><td><a href="hooks.html">② PostSync / PostDelete</a></td><td>△ CR 消滅前</td><td>◎ controller が再実行</td><td>△ backoffLimit</td><td>△ sync ごとに実行</td><td>× 失敗で削除が詰まる</td><td>× 全アプリのマニフェスト</td><td>× 自前</td><td>△ 自前</td><td>△ 資格情報がアプリごと</td><td>△ アプリごとに Job</td><td>△ 0.8 秒＋CR 消滅は後</td></tr>
<tr><td><a href="knative.html">③ Knative</a></td><td>○ DELETE</td><td>× 停止中は取りこぼす</td><td>◎ retry・backoff・DLQ</td><td>○ 永続 Broker で at-least-once</td><td>○ 制御面・Kafka 系は HA、adapter は 1</td><td>◎ Trigger を足すだけ</td><td>◎ データプレーン水平</td><td>◎ OTLP・CloudEvents</td><td>○ ns 内で完結、偽装に EventPolicy</td><td>△ 部品が多い</td><td>◎ 5 ms</td></tr>
<tr><td><a href="argo-events.html">④ Argo Events</a></td><td>○ DELETE</td><td>× 停止中は取りこぼす</td><td>○ retry・dlqTrigger</td><td>△ 既定 at-most-once</td><td>○ Active-Passive</td><td>○ Sensor の編集</td><td>○ Sensor 単位</td><td>△ Prometheus</td><td>○ ns 内で完結</td><td>△ EventBus が要る</td><td>◎ 7 ms</td></tr>
<tr><td><a href="finalizer.html">⑤ finalizer（Metacontroller）</a></td><td>◎ 消滅を保証</td><td>◎ 復旧後に拾う</td><td>○ 送れるまで呼び直す</td><td>◎ at-least-once＋uid</td><td>× 止まると削除も止まる</td><td>○ Broker に出せば ◎</td><td>△ 単一リーダー</td><td>○ hook で OTel</td><td>△ ClusterRole を絞る</td><td>○ hook 1 つ</td><td>○ 約 10 ms</td></tr>
<tr><td><strong>推奨: Knative で観測</strong><br>ApiServerSource＋突き合わせ</td><td>◎ Namespace の消滅</td><td>○ 突き合わせが拾う</td><td>◎ Broker の retry・DLQ</td><td>◎ 決定的 id</td><td>○ 削除を止めない</td><td>◎ Trigger を足すだけ</td><td>◎ データプレーン水平</td><td>◎ CloudEvents</td><td>◎ get/list/watch のみ</td><td>○ 部品 3 つ</td><td>◎ 即時（安全網は 1 分）</td></tr>
<tr><td><a href="api-stream.html">⑥ API stream</a></td><td>○ DELETED</td><td>× 取りこぼす</td><td>× 無い</td><td>× 詰まると捨てる</td><td>△ 自前</td><td>△ 自前</td><td>△ 自前</td><td>△ 自前</td><td>○ Argo CD の RBAC で絞られる</td><td>× 自作</td><td>◎ 2 ms</td></tr>
</tbody>
</table>
</div>

採点の根拠は各方式のページに、基準は[評価軸と採点基準](criteria.html)に書いた。表を縦に読むと、watch 系（③④⑥）は検知層が全部 × で、違いが出るのは配送層から後になる。finalizer 方式（⑤）はその逆で、検知層は ◎ だが、可用性と運用負荷を自分で背負う。推奨構成では ⑤ で削除完了を確実に取り、配送が必要になったら ③ の配送層（Broker）だけを借りる。

---


### 取りこぼす条件

| 取りこぼす条件 | ApiServerSource だけ | 突き合わせだけ | 両方（突き合わせが ADD も記録） | 根拠 |
|---|---|---|---|---|
| 受信役（adapter）が止まっている間の削除 | **取りこぼす** | 拾う | 拾う | run15-B |
| 1 周期のうちに作られて消えた Namespace | 拾う | **取りこぼす** | 拾う（ADD で一覧に載る） | run15-C |
| adapter が、その Namespace の生存期間中ずっと止まっていた | 取りこぼす | 1 周期より短ければ取りこぼす | **取りこぼす**（ADD も DELETE も届かない） | run15-D |
| uid 一覧の保存先を失った | 影響なし | **取りこぼす**（前回の状態が無い） | 取りこぼす（DELETE だけは届く） | 設計上 |
| 一覧を送信より先に更新した | 影響なし | **取りこぼす** | 取りこぼしうる | 設計上。送ってから保存する（at-least-once） |
| Broker が InMemoryChannel | Broker の再起動で**失う** | 同左 | 同左 | InMemoryChannel の README（"No Persistence"） |
| adapter の送信が失敗した | **失う**（ログを出して終わる） | 次の周期で送り直す | 拾う | `delegate.go` の `sendCloudEvent` |

突き合わせ用の Service が ApiServerSource の ADD も一覧に記録すると、短命な Namespace も拾える。残る取りこぼしは「受信役が、その Namespace の生存期間中ずっと止まっていた」場合だけに縮む（run15-C・D）。


### 変更のたびに基盤側の設定を触るか {#change-summary}

| 方式 | 宛先の追加 | 条件の変更 | 送信内容の変更 |
|---|---|---|---|
| **推奨（Knative で観測）** | 通知側（アプリの Trigger） | 通知側（観測 Service） | 通知側（観測 Service か EventTransform） |
| ① Notifications | 基盤側（`argocd-notifications-cm`）。self-service なら通知側 | 基盤側（trigger） | 基盤側（template） |
| ② PostSync / PostDelete | 全アプリのマニフェスト | 同左 | 同左 |
| ③ Knative ApiServerSource 単体 | 通知側 | 通知側 | 通知側 |
| ④ Argo Events | 通知側（Sensor） | 通知側 | 通知側 |
| ⑤ finalizer | 通知側（Broker を挟めば） | 基盤側の部品（コントローラ） | 基盤側の部品 |
| ⑥ API stream | 通知側（自前クライアント） | 同左 | 同左 |

採点の基準は [評価軸と採点基準](criteria.html) にある。

---

## ページ一覧

| ページ | 中身 |
|---|---|
| [推奨構成の詳細](recommended.html) | 構成の各部、経路を 1 本にする場合、設計の原則、デプロイ完了の取り方、削除完了の定義、複数モジュール、採らない案、基盤側の負荷、Broker の永続化の選択肢、通信規格、運用保守 |
| [評価軸と採点基準](criteria.html) | 評価軸の出典、各軸の ◎○△× の基準、変更時の作業の採点、選定基準、既存の推奨・事例 |
| [実測の報告書](report.html) | run1〜run19 の目的・手順・結果・解釈、検証環境、グラレコ、問いと run の対応 |
| [① Argo CD Notifications](notifications.html) | trigger・template・service。Argo CD の設定を持つチームが通知も持つ場合の代替 |
| [② PostSync / PostDelete Job](hooks.html) | hook の Job から送る |
| [③ Knative Eventing](knative.html) | Knative の保証の範囲と、取りこぼす理由 |
| [④ Argo Events](argo-events.html) | EventSource → EventBus → Sensor |
| [⑤ finalizer 方式](finalizer.html) | Metacontroller / 自作。削除を Application の消滅で定義する場合の代替 |
| [⑥ Argo CD API stream](api-stream.html) | /api/v1/stream/applications |

---

## 推奨構成の図

```diagram
title: 推奨構成
caption: 図 1 推奨構成。基盤側の設定（Argo CD・Notifications・Namespace 削除の Job）には手を入れず、観測だけで取る。入口は Broker 1 つ
height: 520
zones:
  - {label: "基盤側（変更しない）", kind: plain, box: [10, 30, 230, 450]}
  - {label: "通知基盤（obs namespace）", kind: platform, box: [260, 30, 400, 450]}
  - {label: "アプリ側の namespace", kind: app, box: [680, 30, 310, 450]}
nodes:
  - {id: job, label: "Namespace 削除の Job", mono: ["delete ns --wait"], box: [25, 60, 200, 54]}
  - {id: ns, kind: app, label: "Namespace（ラベル付き）", mono: ["Terminating → 消滅"], box: [25, 150, 200, 60]}
  - {id: app, kind: app, label: "Application", mono: ["Synced / Healthy / revision"], box: [25, 300, 200, 60]}
  - {id: src, label: "ApiServerSource", mono: ["Namespace と Application"], box: [275, 60, 180, 54]}
  - {id: ping, label: "PingSource（毎分）", box: [470, 60, 175, 44]}
  - {id: obs, label: "観測 Service", mono: ["判定・突き合わせ"], box: [470, 140, 175, 54]}
  - {id: inv, kind: state, label: "uid 一覧", mono: ["ConfigMap"], box: [470, 225, 175, 50]}
  - {id: brk, kind: state, label: "Broker（入口 1 つ）", mono: ["永続化した土台"], box: [275, 300, 180, 60]}
  - {id: tf, label: "EventTransform", mono: ["id = uid:deleted"], box: [275, 170, 180, 54]}
  - {id: tr, label: "Trigger（宛先ごと）", mono: ["delivery: retry / DLQ"], box: [695, 300, 280, 60]}
  - {id: rcv, kind: ext, label: "宛先（Slack / 社内 API）", mono: ["id で重複を消す"], box: [695, 400, 280, 54]}
edges:
  - {from: job, to: ns, kind: http, label: "削除"}
  - {from: src, to: ns, kind: watch, via: [[250, 87], [250, 180]]}
  - {from: src, to: app, kind: watch, via: [[250, 100], [250, 330]], label: watch, dy: 60}
  - {from: ping, to: obs, kind: ce}
  - {from: obs, to: inv, kind: patch}
  - {from: src, to: brk, kind: ce, via: [[265, 87], [265, 330]]}
  - {from: brk, to: tf, kind: ce, label: "delete"}
  - {from: brk, to: obs, kind: ce, via: [[460, 315], [460, 167]], label: "add/update", dx: -2, dy: 50}
  - {from: obs, to: brk, kind: ce, via: [[555, 345]], label: "deployed / deleted"}
  - {from: brk, to: tr, kind: ce}
  - {from: tr, to: rcv, kind: ce}
```
