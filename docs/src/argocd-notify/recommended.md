# 推奨構成の詳細

> 概要ページの結論の中身。構成の各部、デプロイ完了と削除完了の取り方、採らない案、基盤側の負荷、通信規格、運用保守。**できること:** 基盤側の設定を触らずに、デプロイ完了と削除完了を取る。**できないこと:** 受信役が、ある Namespace の生存期間中ずっと止まっていた場合は、その削除を取れない。

<p class="eli5">これまでの方法では、通知を一つ足すたびに、基盤チームの Namespace（argocd）にある設定を書き換えてもらう必要がありました。推奨構成では線を引き直します。基盤チームは「見張り役」と「郵便局（Broker）」と、チームごとの転送を一本だけ持ちます。あなたは自分の Namespace に、振り分けの決まり（Trigger）と、Slack の鍵を入れた Secret と、受け手の Pod を置くだけです。宛先を足すのも、条件を変えるのも、自分の Namespace の中で終わります。</p>

<!-- archify: recommended.architecture -->

**図の読み方**

- ① Namespace を消すのは基盤の既存 Job。推奨構成はこれを観測するだけ
- ② ApiServerSource（基盤側）。⚠ 停止中の削除を落とす（取りこぼす条件の表）
- ③ 観測 Service が PingSource で毎分照合し、②で落ちた分を拾う
- ④ Broker（基盤側）。⚠ InMemoryChannel だと失う。永続化した土台を使う
- ⑤⑥ 利用者側は Trigger・受け手・Secret を自分の Namespace に置く。基盤に頼むのは転送 1 本だけ

（色と線の読み方: 橙の破線の枠が基盤側、赤の破線の枠が利用者側。緑の線は主な流れ、赤の線と「⚠」は問題点、紫の破線は鍵などの参照。）




[このページを一言で（たとえ話と図）](index.html#grareco) は概要ページにある。

## 推奨構成のアーキテクチャ

この調査の主張は次のとおり。基盤側と利用者側では、管理するリソースが違う。従来の方式では、通知の設定に要る主なリソース（`argocd-notifications-cm` など）が基盤側にあるので、利用者からは設定しにくい。推奨構成は、利用者が自分の namespace のリソースだけで通知を設定できるようにする。

図は見方ごとに 4 枚に分けた。

| 図 | 見方 |
|---|---|
| 図 1 | データの流れ |
| 図 2 | 責任範囲（どちらが何を管理するか） |
| 図 3・図 4 | 利用者が通知を足すときの Before / After |

### データの流れ

```diagram
title: 推奨構成のデータの流れ
caption: 図 1 データの流れ（概要ページの図 1 と同じ構成）。基盤側の既存部品には手を入れず、通知基盤が観測して Broker に送る。宛先への配送は利用者側が持つ
height: 640
zones:
  - {label: "基盤側：既存の部品（通知のために変更しない）", kind: plain, box: [10, 30, 300, 560]}
  - {label: "基盤側：通知基盤（obs / knative-eventing）", kind: platform, box: [330, 30, 330, 560]}
  - {label: "利用者側（アプリの namespace）", kind: app, box: [680, 30, 310, 560]}
nodes:
  - {id: argo, label: "Argo CD", mono: ["application-controller"], box: [25, 60, 270, 54]}
  - {id: app, kind: app, label: "Application", mono: ["Synced / Healthy / revision"], box: [25, 140, 270, 54]}
  - {id: job, label: "Namespace 削除の Job", mono: ["delete ns --wait"], box: [25, 240, 270, 54]}
  - {id: ns, kind: app, label: "Namespace（ラベル付き）", mono: ["Terminating → 消滅"], box: [25, 320, 270, 54]}
  - {id: unused, kind: crd, label: "使わない部品（代替として残す）", mono: ["Notifications（① の代替）", "Metacontroller / finalizer（⑤）"], box: [25, 480, 270, 70]}
  - {id: src, label: "ApiServerSource", mono: ["Application と Namespace を watch"], box: [345, 60, 300, 54]}
  - {id: obs, label: "観測 Service", mono: ["デプロイ完了の判定・突き合わせ"], box: [345, 150, 300, 54]}
  - {id: ping, label: "PingSource（毎分）", box: [345, 235, 140, 44]}
  - {id: inv, kind: state, label: "uid 一覧", mono: ["ConfigMap"], box: [505, 235, 140, 50]}
  - {id: tf, label: "EventTransform", mono: ["delete → id = uid:deleted"], box: [345, 320, 300, 54]}
  - {id: brk, kind: state, label: "Broker（入口 1 つ）", mono: ["永続化した土台"], box: [345, 420, 300, 60]}
  - {id: abrk, label: "アプリの Broker", box: [695, 420, 280, 44]}
  - {id: tr, label: "Trigger（宛先ごと）", mono: ["delivery: retry / DLQ"], box: [695, 300, 280, 54]}
  - {id: rcv, kind: ext, label: "宛先（Slack / 社内 API）", mono: ["id で重複を消す"], box: [695, 180, 280, 54]}
  - {id: dlq, kind: ext, label: "DLQ", box: [695, 60, 280, 44]}
edges:
  - {from: argo, to: app, kind: patch}
  - {from: job, to: ns, kind: http, label: "削除"}
  - {from: src, to: app, kind: watch, label: watch, dy: -8}
  - {from: src, to: ns, kind: watch, via: [[320, 100], [320, 347]]}
  - {from: brk, to: obs, kind: ce, via: [[655, 450], [655, 177]], label: "add / update", dx: 0}
  - {from: ping, to: obs, kind: ce}
  - {from: obs, to: inv, kind: patch}
  - {from: obs, to: brk, kind: ce, via: [[365, 215], [365, 420]], label: "deployed / deleted", dx: 45}
  - {from: brk, to: tf, kind: ce, via: [[560, 420], [560, 374]], label: "delete", dx: 18}
  - {from: brk, to: abrk, kind: ce, label: "転送"}
  - {from: abrk, to: tr, kind: ce}
  - {from: tr, to: rcv, kind: ce}
  - {from: tr, to: dlq, kind: ce, via: [[985, 327], [985, 82]]}
notes:
  - [345, 520, "デプロイ完了: Application の add/update → 観測 Service → id = uid:revision:deployed"]
  - [345, 538, "削除完了: Namespace の delete → EventTransform → id = uid:deleted"]
  - [345, 556, "安全網: PingSource → 観測 Service が list と uid 一覧を比べて同じ id で送る"]
```

### 責任範囲（SoW）

```diagram
title: 責任範囲
caption: 図 2 責任範囲。太い破線の左が基盤側、右が利用者側。リソースを管理する側に置いた（推奨構成）
height: 620
dividers:
  - {line: [640, 30, 640, 590], labels: [[230, 24, "基盤側（Platform チーム）が管理"], [700, 24, "利用者側（App チーム）が管理"]]}
zones:
  - {label: "クラスタスコープ", kind: platform, box: [10, 40, 300, 260]}
  - {label: "argocd namespace", kind: platform, box: [320, 40, 300, 260]}
  - {label: "obs namespace（通知基盤）", kind: platform, box: [10, 315, 610, 270]}
  - {label: "アプリの namespace（例 team-a）", kind: app, box: [660, 40, 330, 545]}
nodes:
  - {id: crd, kind: crd, label: "CRD", mono: ["Argo CD・Knative Eventing"], box: [25, 70, 270, 44]}
  - {id: cr, kind: crd, label: "ClusterRole / RoleBinding", mono: ["namespaces・applications の読み取り"], box: [25, 125, 270, 44]}
  - {id: ns, kind: app, label: "Namespace（ラベル付き）", mono: ["作成・削除は基盤"], box: [25, 180, 270, 44]}
  - {id: job, label: "Namespace 削除の Job", box: [25, 235, 270, 44]}
  - {id: app, kind: app, label: "Application", mono: ["spec と status"], box: [335, 70, 270, 44]}
  - {id: proj, kind: crd, label: "AppProject", box: [335, 125, 270, 44]}
  - {id: ncm, kind: crd, label: "argocd-notifications-cm", mono: ["推奨構成では使わない"], box: [335, 180, 270, 44]}
  - {id: nsec, kind: crd, label: "argocd-notifications-secret", mono: ["推奨構成では使わない"], box: [335, 235, 270, 44]}
  - {id: src, label: "ApiServerSource", box: [25, 345, 280, 44]}
  - {id: obs, label: "観測 Service", mono: ["判定と突き合わせ"], box: [25, 400, 280, 44]}
  - {id: ping, label: "PingSource", box: [25, 455, 280, 44]}
  - {id: brk, kind: state, label: "Broker（入口）", box: [335, 345, 270, 44]}
  - {id: tf, label: "EventTransform", mono: ["id を決める"], box: [335, 400, 270, 44]}
  - {id: inv, kind: state, label: "uid 一覧（ConfigMap）", box: [335, 455, 270, 44]}
  - {id: fwd, label: "転送 Trigger（チームごとに 1 本）", mono: ["チームの登録時に基盤が置く"], box: [25, 515, 580, 44]}
  - {id: abrk, kind: state, label: "Broker（アプリ用）", box: [675, 70, 300, 44]}
  - {id: tr, kind: crd, label: "Trigger（宛先ごと）", mono: ["filter（type・subject）"], box: [675, 125, 300, 44]}
  - {id: dl, kind: crd, label: "delivery", mono: ["retry・backoff・DLQ"], box: [675, 180, 300, 44]}
  - {id: et, kind: crd, label: "EventTransform（任意）", mono: ["宛先ごとの本文の整形"], box: [675, 235, 300, 44]}
  - {id: rcv, kind: ext, label: "受け手 Service", mono: ["id で重複を消す"], box: [675, 290, 300, 44]}
  - {id: sec, kind: state, label: "Secret", mono: ["Slack の webhook など"], box: [675, 345, 300, 44]}
  - {id: dq, kind: ext, label: "DLQ の受け口", box: [675, 400, 300, 44]}
edges:
  - {from: fwd, to: abrk, kind: ce, via: [[640, 537], [640, 92]], label: "転送", dx: 0, dy: 200}
```

| リソース | 管理する側 | 置き場所 | 利用者が通知の設定で触るか |
|---|---|---|---|
| CRD（Argo CD・Knative）、ClusterRole | 基盤 | クラスタスコープ | 触らない |
| Namespace と、それを消す Job | 基盤 | クラスタスコープ | 触らない |
| Application、AppProject | 基盤 | argocd | 触らない |
| `argocd-notifications-cm`、`argocd-notifications-secret` | 基盤 | argocd | 触らない（推奨構成では使わない） |
| ApiServerSource、観測 Service、PingSource、EventTransform、Broker（入口）、uid 一覧 | 基盤（通知基盤） | obs | 触らない |
| 転送 Trigger | 基盤 | obs | 触らない（チームを登録するとき、基盤が 1 本置く） |
| Broker（アプリ用）、Trigger、delivery、EventTransform、受け手、Secret、DLQ | 利用者 | アプリの namespace | ここだけを触る |

### Before / After：利用者が Slack 通知を足すとき

```diagram
title: Before
caption: 図 3 Before（Notifications で通知を足す場合）。赤い破線は、利用者が基盤側のリソースに手を入れる必要がある箇所（依頼か、権限の付与が要る）
height: 470
dividers:
  - {line: [640, 30, 640, 345], labels: [[250, 24, "基盤側"], [760, 24, "利用者側"]]}
zones:
  - {label: "argocd namespace（基盤が管理）", kind: platform, box: [10, 40, 610, 300]}
  - {label: "アプリの namespace", kind: app, box: [660, 40, 330, 300]}
nodes:
  - {id: cm, kind: bad, label: "argocd-notifications-cm", mono: ["service・template・trigger を追記"], box: [25, 70, 280, 54]}
  - {id: sec, kind: bad, label: "argocd-notifications-secret", mono: ["Slack のトークンを追記"], box: [25, 150, 280, 54]}
  - {id: app, kind: bad, label: "Application", mono: ["subscribe annotation を追記"], box: [25, 230, 280, 54]}
  - {id: flag, kind: bad, label: "argocd-cmd-params-cm", mono: ["self-service を有効にする（初回）"], box: [325, 70, 280, 54]}
  - {id: proj, kind: bad, label: "AppProject", mono: ["sourceNamespaces に追加（初回）"], box: [325, 150, 280, 54]}
  - {id: ncc, label: "notifications-controller", mono: ["argocd の設定を読んで送る"], box: [325, 230, 280, 54]}
  - {id: user, kind: app, label: "利用者（App チーム）", mono: ["Slack に通知したい"], box: [675, 70, 300, 54]}
  - {id: none, label: "自分の namespace に", lines: ["通知の設定の置き場が無い"], mono: ["（self-service を有効にするまで）"], box: [675, 150, 300, 70]}
edges:
  - {from: user, to: cm, kind: bad, via: [[640, 137], [165, 137]], label: "編集が要る", dx: 120, dy: 0}
  - {from: user, to: flag, kind: bad, via: [[640, 137], [465, 137]]}
  - {from: user, to: sec, kind: bad, via: [[640, 217], [165, 217]]}
  - {from: user, to: proj, kind: bad, via: [[640, 217], [465, 217]]}
  - {from: user, to: app, kind: bad, via: [[640, 297], [165, 297]]}
notes:
  - [20, 368, "詰まる点 1: 宛先・条件・本文の変更のたびに、argocd namespace の ConfigMap を基盤に編集してもらう"]
  - [20, 386, "詰まる点 2: 送信先の資格情報を、基盤の Secret に預けることになる"]
  - [20, 404, "詰まる点 3: self-service を使うには、基盤側の設定（フラグと AppProject）が先に要る"]
  - [20, 422, "詰まる点 4: Application の annotation を足すには、argocd の applications への patch 権限が要る（run9 では付与されていなかった）"]
```

```diagram
title: After
caption: 図 4 After（推奨構成）。利用者は自分の namespace のリソースだけを作る。基盤側は、通知の追加・変更では何も変えない
height: 470
dividers:
  - {line: [640, 30, 640, 345], labels: [[250, 24, "基盤側（変更なし）"], [760, 24, "利用者側"]]}
zones:
  - {label: "argocd namespace", kind: platform, box: [10, 40, 300, 300]}
  - {label: "obs namespace（通知基盤）", kind: platform, box: [320, 40, 300, 300]}
  - {label: "アプリの namespace", kind: app, box: [660, 40, 330, 300]}
nodes:
  - {id: cm, kind: crd, label: "argocd-notifications-cm", mono: ["触らない"], box: [25, 70, 270, 44]}
  - {id: app, kind: app, label: "Application", mono: ["annotation も不要"], box: [25, 135, 270, 44]}
  - {id: proj, kind: crd, label: "AppProject・RBAC", mono: ["触らない"], box: [25, 200, 270, 44]}
  - {id: src, label: "ApiServerSource・観測 Service", mono: ["全チーム共通"], box: [335, 70, 270, 44]}
  - {id: brk, kind: state, label: "Broker（入口）", box: [335, 135, 270, 44]}
  - {id: fwd, label: "転送 Trigger", mono: ["チームの登録時に 1 本だけ"], box: [335, 200, 270, 44]}
  - {id: user, kind: app, label: "利用者（App チーム）", mono: ["自分の namespace だけを触る"], box: [675, 60, 300, 44]}
  - {id: abrk, kind: state, label: "Broker", box: [675, 125, 140, 44]}
  - {id: tr, kind: crd, label: "Trigger", mono: ["filter・DLQ"], box: [835, 125, 140, 44]}
  - {id: rcv, kind: ext, label: "受け手", mono: ["Slack へ送る"], box: [675, 200, 140, 44]}
  - {id: sec, kind: state, label: "Secret", mono: ["Slack の資格情報"], box: [835, 200, 140, 44]}
edges:
  - {from: src, to: brk, kind: ce}
  - {from: brk, to: fwd, kind: ce}
  - {from: fwd, to: abrk, kind: ce, via: [[640, 222], [640, 147]], label: "転送", dx: 0, dy: -40}
  - {from: abrk, to: tr, kind: ce}
  - {from: tr, to: rcv, kind: ce}
  - {from: sec, to: rcv, kind: rbac}
notes:
  - [20, 368, "宛先の追加: 自分の namespace に Trigger・受け手・Secret を足す"]
  - [20, 386, "条件の変更: Trigger の filter（type・subject などの属性）を変える"]
  - [20, 404, "本文の変更: 自分の namespace の EventTransform か受け手で整形する"]
  - [20, 422, "基盤に頼むのは、チームを初めて登録するときの転送 Trigger 1 本だけ"]
```

| 作業 | Before（Notifications） | After（推奨構成） |
|---|---|---|
| 宛先を足す | 基盤の `argocd-notifications-cm`（service）と `-secret` を編集。Application に subscribe annotation を付ける | 自分の namespace に Trigger・受け手・Secret を足す |
| 条件を変える | 基盤の `argocd-notifications-cm`（trigger）を編集 | 自分の Trigger の filter を変える |
| 本文を変える | 基盤の `argocd-notifications-cm`（template）を編集 | 自分の EventTransform か受け手を変える |
| 資格情報の置き場所 | 基盤の Secret（self-service なら自分の namespace） | 自分の namespace の Secret |
| 基盤に頼むこと | 上のすべて（self-service なら、初回のフラグと AppProject） | チームの登録時に転送 Trigger を 1 本 |

**利用者の範囲外に残るもの:** 「デプロイ完了とは何か」という判定そのもの（観測 Service の条件）は、通知基盤（obs）の持ち物で、全チームに共通する。利用者が変えられるのは、届いたイベントのうち何を受けるか（filter）と、どう整形するかまで。判定を変えるときは、基盤の通知基盤を変えることになる。ただし Argo CD の設定には触れない。



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

