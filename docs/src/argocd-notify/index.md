# Argo CD Application の完了通知

> Argo CD の `Application` について、デプロイ完了（Synced かつ Healthy）と削除完了（finalizer の処理が終わってオブジェクトと管理リソースが実際に消えた時点）を検知し、外部へ送る 6 つの方式を比べる。根拠は kind 上の Argo CD v3.5.3 での実測と、各プロジェクトのソース・公式ドキュメント。方式ごとの詳細は各ページに分けた。

## グラレコ {#grareco}

<div class="grwb">
<svg class="wb" viewBox="0 0 1000 600" role="img" aria-label="グラレコ：Namespace の消滅を、基盤に触らず外から見張って届ける">
<path class="hl" d="M40,52 L560,48"/>
<text class="th" x="40" y="58">消えたら、ちゃんと知らせる</text>
<text class="ts" x="600" y="56">基盤に触らず、外から見張る</text>

<g filter="url(#wob)">
  <!-- 境界線 -->
  <path class="wk" d="M662,92 C656,180 668,260 660,340 C654,420 666,500 660,580"/>
  <!-- Namespace が消える -->
  <rect class="wk dash" x="40" y="120" width="150" height="96" rx="8"/>
  <path class="wk thin" d="M58,140 L100,140 M58,158 L130,158 M58,176 L112,176"/>
  <g transform="rotate(-28 170 214)"><rect class="wk fr" x="146" y="198" width="56" height="30" rx="4"/><path class="wk thin" d="M146,212 L202,212"/></g>
  <path class="wk thin" d="M112,236 q12,8 24,0 q12,8 24,0"/>
  <!-- 見張る目 -->
  <path class="wb-b fb" d="M250,166 Q300,122 350,166 Q300,210 250,166 Z"/>
  <circle class="fk" cx="300" cy="166" r="11"/>
  <path class="wb-b thin dash" d="M248,166 L194,168"/>
  <!-- 寝ている間に落ちる封筒 -->
  <path class="wr thin" d="M258,252 l30,0 l0,20 l-30,0 z M258,252 l15,11 l15,-11"/>
  <path class="wr dash thin" d="M273,218 L273,248"/>
  <!-- 安全網 -->
  <path class="wb-b" d="M190,320 Q280,360 370,320"/>
  <path class="wb-b thin" d="M205,327 L225,343 M235,335 L250,350 M265,340 L275,352 M295,340 L300,352 M325,336 L322,350 M352,328 L345,344 M215,338 L360,334"/>
  <circle class="wk fw" cx="120" cy="330" r="30"/>
  <path class="wk" d="M120,330 L120,310 M120,330 L134,338"/>
  <!-- Broker -->
  <path class="wb-b fb" d="M430,210 L600,210 L600,300 L430,300 Z"/>
  <path class="wb-b" d="M430,210 Q515,186 600,210"/>
  <path class="wb-b thick" d="M354,166 C400,166 420,200 440,222" marker-end="url(#ab)"/>
  <path class="wb-b" d="M372,322 C410,318 420,290 440,282" marker-end="url(#ab)"/>
  <!-- 同じ id の封筒 2 通 → 1 通 -->
  <path class="wk thin" d="M452,236 l26,0 l0,17 l-26,0 z M452,236 l13,9 l13,-9"/>
  <path class="wk thin" d="M452,262 l26,0 l0,17 l-26,0 z M452,262 l13,9 l13,-9"/>
  <path class="wk thin" d="M486,256 L520,256" marker-end="url(#ak)"/>
  <path class="wk thin" d="M530,246 l30,0 l0,20 l-30,0 z M530,246 l15,11 l15,-11"/>
  <!-- 境界を越えて利用者側へ -->
  <path class="wb-b" d="M604,254 C640,254 660,230 700,226" marker-end="url(#ab)"/>
  <!-- 利用者の Trigger（じょうご） -->
  <path class="wk fw" d="M704,190 L800,190 L770,240 L770,272 L734,272 L734,240 Z"/>
  <path class="wk" d="M752,276 C752,320 800,330 840,318" marker-end="url(#ak)"/>
  <path class="wk" d="M752,276 C752,360 780,400 830,408" marker-end="url(#ak)"/>
  <!-- 宛先 -->
  <path class="wk fw" d="M846,292 h110 a10,10 0 0 1 10,10 v36 a10,10 0 0 1 -10,10 h-86 l-16,14 l4,-14 h-12 a10,10 0 0 1 -10,-10 v-36 a10,10 0 0 1 10,-10 z"/>
  <rect class="wk fw" x="838" y="388" width="120" height="44" rx="6"/>
  <!-- 利用者 -->
  <circle class="wk fw" cx="890" cy="482" r="18"/>
  <path class="wk" d="M890,500 L890,548 M890,516 L862,534 M890,516 L920,504 M890,548 L872,576 M890,548 L906,576"/>
  <path class="wk" d="M922,496 l12,-8 l4,6 M934,488 l8,-4"/>
  <!-- 触らない ConfigMap -->
  <path class="wk fw" d="M430,420 l120,0 l0,90 l-120,0 z"/>
  <path class="wk thin" d="M446,446 l80,0 M446,466 l90,0 M446,486 l60,0"/>
  <path class="wr" d="M420,410 L560,520 M560,410 L420,520"/>
  <!-- on-deleted は早すぎ -->
  <circle class="wr" cx="90" cy="460" r="34"/>
  <path class="wr" d="M66,436 L114,484"/>
</g>

<text class="ts" x="54" y="112">Namespace</text>
<text class="ts" x="40" y="264">消える</text>
<text class="ts tb" x="276" y="110">watch</text>
<text class="ts tr" x="296" y="268">止まってる間…</text>
<text class="ts tb" x="208" y="386">突き合わせで拾う</text>
<text class="ts" x="96" y="378">毎分</text>
<text class="tb" x="480" y="190">Broker</text>
<text class="ts" x="452" y="352">同じ id → 1 通</text>
<text class="ts" x="808" y="220">Trigger</text>
<text x="866" y="324">Slack</text>
<text class="ts" x="852" y="416">社内 API</text>
<text class="tb" x="440" y="110">基盤</text>
<text x="690" y="110">利用者</text>
<text class="ts" x="740" y="560">自分の ns だけ</text>
<text class="ts tr" x="416" y="540">notifications-cm は触らない</text>
<text class="ts tr" x="40" y="522">on-deleted は</text>
<text class="ts tr" x="40" y="542">「消え始め」</text>
</svg>
</div>

---

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
