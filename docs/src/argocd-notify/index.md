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

## グラレコ {#grareco}

<div class="dgm gr">
<div class="cap">グラレコ: この調査を 1 枚で</div>
<svg class="fig" viewBox="0 0 1000 760" role="img" aria-label="グラフィックレコーディング">
  <defs>
    <marker id="gr-ar" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="8" markerHeight="8" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="gr-ink"/></marker>
  </defs>
  <!-- タイトル帯 -->
  <path class="gr-hl" d="M40,52 C260,40 620,58 960,46 L962,78 C640,90 300,72 38,84 Z"/>
  <text class="gr-title" x="500" y="74" text-anchor="middle">Argo CD の「できた！」「消えた！」を外に知らせるには？</text>

  <!-- 1. 問い: Application くん -->
  <g transform="translate(40,120)">
    <rect class="gr-body" x="0" y="20" width="110" height="90" rx="14"/>
    <circle class="gr-dot" cx="35" cy="55" r="5"/><circle class="gr-dot" cx="75" cy="55" r="5"/>
    <path class="gr-line" d="M35,80 Q55,95 75,80"/>
    <text class="gr-s" x="55" y="130" text-anchor="middle">Application</text>
    <path class="gr-bubble" d="M130,0 h230 a12,12 0 0 1 12,12 v70 a12,12 0 0 1 -12,12 h-200 l-26,22 l4,-22 h-8 a12,12 0 0 1 -12,-12 v-70 a12,12 0 0 1 12,-12 z"/>
    <text class="gr-m" x="148" y="30">デプロイできた！</text>
    <text class="gr-m" x="148" y="54">Namespace 消えた！…を</text>
    <text class="gr-m" x="148" y="78">Slack や社内 API に伝えたい</text>
  </g>

  <!-- 2. 落とし穴 -->
  <g transform="translate(470,110)">
    <path class="gr-warn" d="M0,150 L60,40 L120,150 Z"/>
    <text class="gr-big gr-red" x="60" y="132" text-anchor="middle">!</text>
    <text class="gr-h gr-red" x="140" y="40">落とし穴 ①</text>
    <text class="gr-m" x="140" y="64"><tspan class="gr-code">on-deleted</tspan> は「消え始め」で鳴る</text>
    <text class="gr-s" x="140" y="86">削除要求から 0.06 秒、まだ何も消えていない</text>
    <text class="gr-h gr-red" x="140" y="118">落とし穴 ②</text>
    <text class="gr-m" x="140" y="142">watch は止まっている間の DELETE を見逃す</text>
    <text class="gr-s" x="140" y="164">Knative / Argo Events / API stream 共通</text>
  </g>

  <path class="gr-sep" d="M30,300 C300,292 700,308 970,298"/>

  <!-- 3. 鍵: finalizer = 消えない約束 -->
  <g transform="translate(40,330)">
    <text class="gr-h" x="0" y="0">ひらめき：触らずに、外から見張る</text>
    <!-- 錠前 -->
    <rect class="gr-lock" x="10" y="40" width="80" height="64" rx="8"/>
    <path class="gr-line2" d="M26,40 v-14 a24,24 0 0 1 48,0 v14"/>
    <circle class="gr-dot" cx="50" cy="70" r="7"/>
    <text class="gr-m" x="110" y="52">基盤の Job にも Namespace にも手を入れない</text>
    <text class="gr-m" x="110" y="76">watch で即時、突き合わせで取りこぼしを拾う</text>
    <text class="gr-s" x="110" y="100">→ 同じ id（uid:deleted）で届くので、受け手が重複を消す</text>
    <!-- 付箋: Metacontroller -->
    <g transform="translate(470,20) rotate(-3)">
      <rect class="gr-note" x="0" y="0" width="256" height="96" rx="4"/>
      <text class="gr-h" x="14" y="28">finalizer は付けない</text>
      <text class="gr-s" x="14" y="52">付けると基盤の Job が通知を待つ</text>
      <text class="gr-s" x="14" y="72">＝密結合。権限も強くなる</text>
    </g>
    <g transform="translate(750,26) rotate(2)">
      <rect class="gr-note2" x="0" y="0" width="200" height="90" rx="4"/>
      <text class="gr-h" x="14" y="28">入口は Broker 1 つ</text>
      <text class="gr-s" x="14" y="52">Trigger はアプリ側に置く</text>
      <text class="gr-s" x="14" y="72">Kafka / RabbitMQ / NATS</text>
    </g>
  </g>

  <path class="gr-sep" d="M30,470 C300,478 700,462 970,472"/>

  <!-- 4. おすすめの流れ -->
  <text class="gr-h" x="40" y="505">おすすめの流れ</text>
  <g transform="translate(40,525)">
    <ellipse class="gr-pill" cx="95" cy="40" rx="95" ry="36"/>
    <text class="gr-m" x="95" y="36" text-anchor="middle">デプロイ完了</text>
    <text class="gr-s" x="95" y="56" text-anchor="middle">Application を観測</text>
    <ellipse class="gr-pill" cx="95" cy="135" rx="95" ry="36"/>
    <text class="gr-m" x="95" y="131" text-anchor="middle">削除完了</text>
    <text class="gr-s" x="95" y="151" text-anchor="middle">ApiServerSource＋突き合わせ</text>
    <path class="gr-arrow" d="M195,45 C290,40 330,80 400,85" marker-end="url(#gr-ar)"/>
    <path class="gr-arrow" d="M195,130 C290,135 330,100 400,95" marker-end="url(#gr-ar)"/>
    <rect class="gr-env" x="410" y="55" width="190" height="70" rx="10"/>
    <path class="gr-line" d="M410,58 L505,100 L600,58"/>
    <text class="gr-s" x="505" y="146" text-anchor="middle">Broker（永続化）→ Trigger</text>
    <text class="gr-s" x="505" y="164" text-anchor="middle">ID = uid で重複を除く</text>
    <path class="gr-arrow" d="M605,90 C680,70 720,40 780,40" marker-end="url(#gr-ar)"/>
    <path class="gr-arrow" d="M605,95 C680,110 720,140 780,140" marker-end="url(#gr-ar)"/>
    <text class="gr-m" x="790" y="45">Slack</text>
    <text class="gr-m" x="790" y="145">社内 API</text>
  </g>

  <!-- 5. 役割分担 -->
  <g transform="translate(40,700)">
    <circle class="gr-head" cx="14" cy="8" r="10"/><path class="gr-line2" d="M14,18 v22 M0,28 h28"/>
    <text class="gr-m" x="40" y="22"><tspan class="gr-b">基盤チーム</tspan>：Knative と観測部品を守る</text>
    <circle class="gr-head gr-head2" cx="534" cy="8" r="10"/><path class="gr-line2" d="M534,18 v22 M520,28 h28"/>
    <text class="gr-m" x="560" y="22"><tspan class="gr-b">利用者</tspan>：Trigger と受け手を持つ</text>
  </g>
</svg>
</div>

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
| [実測の報告書](report.html) | run1〜run19 の目的・手順・結果・解釈、検証環境、問いと run の対応 |
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
