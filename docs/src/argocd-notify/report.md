# 実測の報告書

> kind 上で行った run1〜run19 の記録。各 run の数字は、scratchpad に保存したログ（`runs/`）から取り直した。ログが保存されていない数字は、その旨を書いた。

## 1. 目的

次の問いに答えるために測った。

| 番号 | 問い |
|---|---|
| Q1 | 削除の**開始**と**完了**を区別して取れるか。各方式はどの時点を捉えるか |
| Q2 | 受け手が止まっている間に起きた削除を、復旧後に拾えるか |
| Q3 | 送信先が失敗したとき、retry・DLQ はどう動くか。削除を止めるか |
| Q4 | 同じ変化が何通届くか。重複を id で消せるか |
| Q5 | 必要な権限はどこまで小さくできるか。他チームの Application を覗けるか、通知を偽装できるか |
| Q6 | デプロイ完了を、基盤側の設定を触らずに Notifications と同じ条件で取れるか |
| Q7 | Namespace の消滅を、基盤の Job を変えずに取れるか |
| Q8 | HA 構成（リーダー選出）で、フェイルオーバー中の削除を取りこぼさないか |

## 2. 結論

<div class="dgm gr">
<div class="cap">図 1 グラレコ: 実測でわかったこと</div>
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

- **削除開始と削除完了は別物（Q1）。** Notifications の `on-deleted` は削除要求から 0.05 秒で発火し、管理リソースは 3.45 秒、Application は 6.80 秒で消えた（run3）。
- **watch 系は、止まっている間の削除を取りこぼす（Q2）。** 突き合わせ（uid 一覧）と finalizer だけが、復旧後に拾った（run4・run5・run12・run13・run15）。
- **Broker に入ったあとの配送は強い（Q3）。** 宛先が 500 を返し続けても、retry のあと DLQ に入り、削除は止まらなかった（run16）。
- **重複は決定的な id で 1 通にできる（Q4）。** 3 経路から同じ id が届いた（run13）。デプロイの観測では、同じ revision へのロールバックで id が衝突した（run19）。
- **観測だけで、基盤側の設定を触らずに取れる（Q6・Q7）。** 権限は get/list/watch だけで済んだ（run15・run19）。

## 3. 検証環境のアーキテクチャ

```diagram
title: 検証環境
caption: 図 2 検証環境（kind 1 ノード）。どの namespace で何が動き、どこで時刻を取ったか
height: 560
zones:
  - {label: "kind ノード（Kubernetes v1.33.1、kind v0.29.0）", kind: plain, box: [10, 30, 980, 490]}
  - {label: "argocd（Argo CD v3.5.3）", kind: platform, box: [25, 55, 300, 200]}
  - {label: "knative-eventing（v1.23.0）", kind: platform, box: [345, 55, 300, 200]}
  - {label: "obs（観測・受け手）", kind: app, box: [665, 55, 310, 450]}
  - {label: "demo / team-a / ラベル付き ns", kind: plain, box: [25, 275, 300, 230]}
  - {label: "その他（run ごとに入れ替え）", kind: plain, box: [345, 275, 300, 230]}
nodes:
  - {id: ctl, label: "application-controller", box: [40, 85, 270, 40]}
  - {id: ncc, label: "notifications-controller", box: [40, 140, 270, 40]}
  - {id: srv, label: "argocd-server（API stream）", box: [40, 195, 270, 40]}
  - {id: brk, label: "Broker（MT・InMemoryChannel）", box: [360, 85, 270, 40]}
  - {id: ping, label: "PingSource", box: [360, 140, 270, 40]}
  - {id: tf, label: "EventTransform（JSONata）", box: [360, 195, 270, 40]}
  - {id: app, kind: app, label: "テスト用チャート", mono: ["ConfigMap・Deployment・hook Job"], box: [40, 305, 270, 54]}
  - {id: nsx, kind: app, label: "ラベル付き Namespace", mono: ["notify.example.com/watch=true"], box: [40, 380, 270, 54]}
  - {id: mc, label: "Metacontroller v4.17.2", box: [360, 305, 270, 40]}
  - {id: ae, label: "Argo Events v1.9.11", box: [360, 360, 270, 40]}
  - {id: fin, label: "自前 finalizer（試作）", box: [360, 415, 270, 40]}
  - {id: src, label: "ApiServerSource adapter", box: [680, 85, 280, 40]}
  - {id: obs, label: "観測 Service / 突き合わせ", box: [680, 145, 280, 40]}
  - {id: chart, label: "Helm リポジトリ（http.server）", box: [680, 205, 280, 40]}
  - {id: rcv, kind: state, label: "受け手（receiver.py）", mono: ["受信時刻・ヘッダを JSON で記録"], box: [680, 270, 280, 60]}
  - {id: wat, kind: state, label: "kubectl watch（ホスト側）", mono: ["Application と管理リソースの", "イベントに時刻を付けて記録"], box: [680, 350, 280, 76]}
edges:
  - {from: ctl, to: app, kind: http}
  - {from: src, to: brk, kind: ce}
  - {from: brk, to: rcv, kind: ce, via: [[655, 105], [655, 300]]}
  - {from: ncc, to: rcv, kind: http, via: [[330, 160], [330, 265], [660, 265], [660, 290]]}
  - {from: wat, to: app, kind: watch, via: [[640, 388], [640, 332], [310, 332]]}
```

**観測の仕組み:**

- **受け手:** 1 つの Pod（`receiver.py`）で全方式の送信を受け、受信時刻（UTC、ミリ秒）・パス・`Ce-*` ヘッダ・本文を 1 行の JSON で記録した。ログは `kubectl logs -f` でホスト側のファイルに保存した。
- **ホスト側の watch:** Application と管理リソースを `kubectl get -w --output-watch-events` で見て、ホストの時刻を付けて記録した。
- **突き合わせ:** 受け手の時刻と watch の時刻は、同じホストの時計で比べた。受け手の Pod もノード上にあるので、時計のずれは ms 未満と見なした（測ってはいない）。
- **操作の時刻:** 削除の発行などの操作時刻は `marks` ファイルに記録した。

## 4. 各 run の結果

各 run を、目的・手順・結果・解釈の順に書く。

### 4.1 run1: Notifications の deployed が届くか {#run1}

- **目的:** Notifications の `on-deployed`（カタログの条件）と PostSync hook が届くかを確かめる（Q1）
- **手順:** `resources-finalizer` 付きの Application を作り、Synced かつ Healthy まで待った
- **結果:**

| 受信 | 時刻 |
|---|---|
| `/postsync`（PostSync hook の Job） | 06:03:01.286 |
| `/notifications/deployed` | 06:03:04.167 |

- **解釈:** PostSync は Healthy のあと、Notifications はその 2.9 秒後、operation が Succeeded になった時点で届いた。この run の削除側（run2）は、セッションが途切れて記録が不完全なので、数字には使わない

### 4.2 run3: ライフサイクル上の時点 {#run3}

- **目的:** 各方式が、作成と削除のどの時点を捉えるかを比べる（Q1・Q4）
- **手順:** 全方式を同時に動かし、Application を作成して、31 秒後に削除した。
  - ホスト側の watch で、Application と管理リソースの時刻を取った
- **結果（表 1、0 秒 = `kubectl delete`）:**

| 出来事 | 時刻 | Application の消滅との差 |
|---|---:|---:|
| `/notifications/deleted`（`on-deleted`） | +0.051 s | −6750 ms |
| 管理リソース（Deployment）の消滅 | +3.450 s | — |
| `/postdelete`（PostDelete hook） | +4.286 s | −2515 ms |
| Application の消滅（watch の DELETED） | +6.801 s | 0 |
| `/knative/delete`（ApiServerSource） | +6.803 s | +2 ms |
| `/argo-events/delete` | +6.803 s | +2 ms |
| API stream の `DELETED` | — | +2 ms |

作成側（0 秒 = 作成）:

| 出来事 | 時刻 | 件数 |
|---|---:|---:|
| `/postsync` | +3.071 s | 1 |
| `/notifications/deployed` | +6.046 s | 1 |
| Knative の `resource.update`（作成から削除開始まで） | — | 14 |
| Argo Events の deployed（データフィルタ） | — | 4（ほかに削除開始の直後に 2） |

時刻は実測（run3・run6）の値。削除側は `kubectl delete` を 0 秒とし、`resources-finalizer.argocd.argoproj.io` 付きで PostDelete hook を 1 つ持つ Application を消した。

<div class="dgm">
<div class="cap">図 3 デプロイ側のタイムライン（run3、0 秒 = Application を作成）</div>
<svg class="fig" viewBox="0 0 1000 250" role="img" aria-label="デプロイのタイムライン">
  <rect class="band" x="240" y="24" width="198" height="18"/>
  <text class="t-mono" x="246" y="37">Sync / Progressing</text>
  <rect class="band" x="440" y="24" width="468" height="18" opacity=".55"/>
  <text class="t-mono" x="446" y="37">Healthy。PostSync hook 実行中、operation は Running</text>
  <line class="ln" x1="240" y1="56" x2="960" y2="56"/>
  <text class="t-mono" x="240" y="72">0s</text><text class="t-mono" x="432" y="72">1.8s</text>
  <text class="t-mono" x="566" y="72">3.1s</text><text class="t-mono" x="896" y="72">6.05s</text>
  <line class="ln ln-dash" x1="438" y1="48" x2="438" y2="236"/>
  <line class="ln ln-dash" x1="910" y1="48" x2="910" y2="236"/>
  <text x="20" y="100">① Notifications on-deployed</text><circle class="mk-ok" cx="910" cy="96" r="6"/><text class="t-mono" x="790" y="100">1 回だけ</text>
  <text x="20" y="130">② PostSync hook（Job）</text><circle class="mk-ok" cx="580" cy="126" r="6"/><text class="t-mono" x="592" y="130">Healthy 後に実行</text>
  <text x="20" y="160">④ Argo Events（UPDATE+filter）</text>
  <circle class="mk-mid" cx="906" cy="156" r="5"/><circle class="mk-mid" cx="912" cy="156" r="5"/><circle class="mk-mid" cx="918" cy="156" r="5"/><circle class="mk-mid" cx="924" cy="156" r="5"/><text class="t-mono" x="790" y="160">4 回届く</text>
  <text x="20" y="190">③ Knative ApiServerSource</text>
  <g class="mk-mid"><circle cx="245" cy="186" r="3"/><circle cx="255" cy="186" r="3"/><circle cx="265" cy="186" r="3"/><circle cx="275" cy="186" r="3"/><circle cx="438" cy="186" r="3"/><circle cx="490" cy="186" r="3"/><circle cx="496" cy="186" r="3"/><circle cx="505" cy="186" r="3"/><circle cx="905" cy="186" r="3"/><circle cx="909" cy="186" r="3"/><circle cx="913" cy="186" r="3"/><circle cx="917" cy="186" r="3"/></g>
  <text class="t-mono" x="600" y="190">更新のたびに update（作成で 14 件）。判定は受け手</text>
  <text x="20" y="220">⑤⑥ 自前 / API stream</text><text class="t-mono" x="240" y="220">MODIFIED を全部受けて自分で判定する（③ と同じ性質）</text>
</svg>
</div>

<div class="dgm">
<div class="cap">図 4 削除側のタイムライン（run3、0 秒 = kubectl delete）</div>
<svg class="fig" viewBox="0 0 1000 300" role="img" aria-label="削除のタイムライン">
  <rect class="band" x="245" y="24" width="355" height="18"/>
  <text class="t-mono" x="251" y="37">管理リソースを削除（resources-finalizer）</text>
  <rect class="band" x="602" y="24" width="333" height="18" opacity=".55"/>
  <text class="t-mono" x="608" y="37">PostDelete hook（post-delete-finalizer）</text>
  <line class="ln" x1="240" y1="56" x2="960" y2="56"/>
  <text class="t-mono" x="236" y="72">0.05s 削除開始</text><text class="t-mono" x="545" y="72">3.5s リソース消滅</text><text class="t-mono" x="880" y="72">6.8s 消滅</text>
  <line class="ln ln-dash" x1="245" y1="48" x2="245" y2="290"/>
  <line class="ln ln-dash" x1="600" y1="48" x2="600" y2="290"/>
  <line class="ln ln-dash" x1="939" y1="48" x2="939" y2="290"/>
  <text x="20" y="100">① on-deleted</text><circle class="mk-bad" cx="246" cy="96" r="6"/><text class="t-mono t-bad" x="258" y="100">削除開始で発火（完了ではない）</text>
  <text x="20" y="128">① カスタム trigger</text><circle class="mk-mid" cx="604" cy="124" r="6"/><text class="t-mono" x="400" y="128">health=Missing で発火 →</text>
  <text x="20" y="156">② PostDelete hook</text><circle class="mk-mid" cx="681" cy="152" r="6"/><text class="t-mono" x="693" y="156">リソース消滅後・CR 消滅前</text>
  <text x="20" y="184">⑤ finalizer 方式</text><circle class="mk-ok" cx="935" cy="180" r="6"/><text class="t-mono" x="700" y="184">残り finalizer が自分だけ →</text>
  <text x="20" y="212">③ Knative delete</text><circle class="mk-ok" cx="940" cy="208" r="6"/><text class="t-mono" x="790" y="212">消滅 +2ms</text>
  <text x="20" y="240">④ Argo Events DELETE</text><circle class="mk-ok" cx="940" cy="236" r="6"/><text class="t-mono" x="790" y="240">消滅 +2ms</text>
  <text x="20" y="268">⑥ API stream DELETED</text><circle class="mk-ok" cx="940" cy="264" r="6"/><text class="t-mono" x="790" y="268">消滅 +2ms</text>
  <text class="t-mono" x="20" y="292">緑: 削除完了　黄: 途中の段階　赤: 削除開始。止まっていた間の取りこぼしは別の軸（検知層の耐障害性）で評価する</text>
</svg>
</div>

Argo CD の `controller/appcontroller.go` の `finalizeApplicationDeletion` は、finalizer を 1 段ずつ外していく。
管理リソースが消え切ると `resources-finalizer.argocd.argoproj.io` を外す。
次に `post-delete-finalizer.argocd.argoproj.io` の段で PostDelete hook を実行し、成功したら外して hook を片付ける。
実測でも finalizer はこの順に外れた（`resources-finalizer` → `post-delete-finalizer` → `post-delete-finalizer/cleanup` → 消滅）。

---


- **解釈:** `on-deleted` は削除開始の時点を捉える。削除完了を捉えたのは、watch 系（Knative・Argo Events・API stream）だけだった。
  - PostDelete hook は、管理リソースが消えたあと、Application が消える前に届いた。
  - Knative の update は 1 回の作成で 14 件来たので、デプロイ完了の判定は受け手が行う必要がある。

### 4.3 run4: 通知系を止めたまま削除（自前 finalizer あり） {#run4}

- **目的:** 止まっている間に削除すると、どの方式が復旧後に拾うかを確かめる（Q2）
- **手順:** 自前 finalizer を付けたうえで、次の 4 つを止めて削除し、25 秒後に復旧させた。
  - Notifications
  - Knative（controller と adapter）
  - Argo Events
  - 自前 finalizer
- **結果（0 秒 = 削除、復旧は +25.1 s）:**

| 受信 | 削除からの時刻 | 復旧からの時刻 |
|---|---:|---:|
| `/postdelete` | +4.8 s | −20283 ms |
| `/finalizer/deleted` | +27.4 s | +2303 ms |
| `/knative/delete` | +27.5 s | +2349 ms |
| Application の消滅（GET が 404） | +27.5 s | +2421 ms |
| Notifications・Argo Events | 届かず | — |

停止中の Application の finalizer は、`["notify.example.com/deletion"]` だけが残っていた。

- **解釈:** finalizer が削除を止めていたので、Knative も、復旧後にまだ残っていた Application の DELETE を送れた。Notifications と Argo Events は送らなかった。

### 4.4 run5: 通知系を止めたまま削除（finalizer なし） {#run5}

- **目的:** finalizer が無い場合の取りこぼしを確かめる（Q2）
- **手順:** run4 と同じ部品を止めて削除し、消滅後に復旧して 90 秒待った
- **結果:** 届いたのは `/postdelete`（削除から +4.2 s）の 1 件だけだった
- **解釈:** watch 系は、止まっている間に消えたものを復旧後に出さない

### 4.5 run6: Notifications のカスタム trigger と自前 finalizer {#run6}

- **目的:** Notifications で取れる最も遅い時点と、finalizer の送信時点を比べる（Q1）
- **手順:** カスタム trigger（`deletionTimestamp != nil and health == Missing`）を足して削除した
- **結果（0 秒 = 削除）:**

| 受信 | 時刻 | Application の消滅との差 |
|---|---:|---:|
| `/notifications/deleted` | +0.050 s | −5545 ms |
| `/notifications/resources-gone`（カスタム） | +4.427 s | −1168 ms |
| `/postdelete` | +5.234 s | −361 ms |
| `/finalizer/deleted` | +5.547 s | −48 ms |
| `/knative/delete` | +5.595 s | 0 ms |
| `/argo-events/delete` | +5.600 s | +5 ms |

- **解釈:** カスタム trigger は、管理リソースが消えた直後に発火した。Notifications では、これより遅い時点は取れない。finalizer は、消滅の 48 ms 前に送った

### 4.6 run7: Notifications から Broker へ CloudEvent {#run7}

- **目的:** Notifications の template で CloudEvent を組み、Broker に入れられるかを確かめる（Q6）
- **手順:** structured mode の本文を Broker ingress に POST する service と template を足し、Application を作成した
- **結果:** `/knative/deployed-ce` に、`Ce-Id: dd455bf2-…-0.1.0`、`Ce-Type: com.example.argocd.app.deployed` で届いた（06:44:39.964）。直接送った `/notifications/deployed` の 4 ms 前
- **解釈:** 送れる。ただし `argocd-notifications-cm` の変更が要る

### 4.7 run8: 宛先の失敗と retry・DLQ {#run8}

- **目的:** 宛先が常に 500 を返すとき、各方式の retry と DLQ を確かめる（Q3）
- **手順:** 宛先を常に 500 にし、Knative の Trigger に `retry: 3`・`exponential`・`PT0.5S`・`deadLetterSink` を設定した
- **結果（ログが残っている部分）:**

| 時刻 | コード | 宛先 |
|---|---:|---|
| 07:38:18.378 | 500 | `/fail/notifications`（1 回目） |
| 07:38:19.381 | 500 | 同 2 回目（+1.0 s） |
| 07:38:21.384 | 500 | 同 3 回目（+2.0 s） |
| 07:38:25.388 | 500 | 同 4 回目（+4.0 s）。以後は送らない |

Knative の削除イベントの retry（初回と 3 回の retry、0.5 → 1 → 2 秒、そのあと DLQ）は、保存したログには最後の 1 回と DLQ しか残っていない。ほかの回は、実行時の画面出力（07:40:56.814〜07:41:00.329）で確認した。Argo Events は、`policy.status.allow` を指定しないと 1 回で終わった。指定すると retry を 3 回行い、`dlqTrigger` に送った（画面出力で確認、ログは保存していない）。

- **解釈:** Notifications は 4 回試したあと送信済みとして記録し、以後は再送しない。Knative は、宣言どおりに retry したあと DLQ に入れた

### 4.8 run9: テナント越境 {#run9}

- **目的:** アプリチームの権限で、他チームの Application を覗けるか、通知を偽装できるかを確かめる（Q5）
- **手順:** `team-a` の ServiceAccount に、`edit` と Knative の namespaced-admin を与えた
- **結果（`kubectl auth can-i` と実際の作成）:**

| 操作 | 結果 |
|---|---|
| argocd の applications を list | no |
| team-a に ApiServerSource・Broker・Trigger・EventSource・Sensor を作成 | yes |
| argocd を見る ApiServerSource | 作れたが、`SufficientPermissions=False` で Ready にならない |
| Platform の Broker に、偽の delete イベントを POST | 202。Platform の受け手まで届いた |

- **解釈:** 覗くことはできない。偽装は、EventPolicy を設定していない既定の状態では防げない

### 4.9 run10: Metacontroller の finalize hook {#run10}

- **目的:** finalizer を Metacontroller で実現した場合の、停止中の削除と宛先の失敗を確かめる（Q2・Q3）
- **手順:** 次の 3 つの場面を順に試した。
  - Metacontroller と hook を止めて削除し、25 秒後に復旧した
  - 宛先を常に 500 にした
  - 通常の状態で削除した
- **結果:**

| 場面 | 結果 |
|---|---|
| 停止中に削除 | 25 秒後も finalizer が残って待った。復旧後の 08:41:16.781 に送信し、08:41:17.463 に消滅 |
| 宛先が 500 | 08:42:00・08:42:04・08:42:34 に再送（500）。削除も待ち、宛先を戻すと 08:43:05 に消滅 |
| 通常 | 送信（08:43:25.393）から消滅（08:43:25.403）まで 10 ms |

- **解釈:** 停止中の削除も拾い、送れるまで削除を止める

### 4.10 run11: 権限を絞った Metacontroller と HA {#run11}

- **目的:** ClusterRole を絞っても動くか、リーダーが変わっても取りこぼさないかを確かめる（Q5・Q8）
- **手順:** ClusterRole を 5 ルールに絞り、`--leader-election` を付けて 2 レプリカで動かした。削除の直前にリーダーを落とした
- **結果:**
  - リーダーは `metacontroller-0` から `metacontroller-1` に移った
  - 削除（09:01:59.273）から消滅（09:02:15.481）まで 16.2 秒
  - 通知は 1 通
  - Lease の期間は 15 秒
  - namespaces の get/list/watch を外すと、list が Forbidden になった（画面出力で確認）
- **解釈:** 絞った権限で動く。フェイルオーバー中の削除も取りこぼさなかった

### 4.11 run12: CronJob による突き合わせ {#run12}

- **目的:** applications の get/list だけで、停止中の削除を拾えるかを確かめる（Q2・Q5）
- **手順:** 毎分の CronJob が uid 一覧（ConfigMap）と list を比べた。通常の削除と、CronJob を止めている間の削除を試した
- **結果:**

| 場面 | 消滅 | 受信 |
|---|---|---|
| 通常 | 09:07:55.837 | 09:08:01.140（+5.3 s、次の周期） |
| CronJob 停止中 | 09:10:39.565 | 再開（09:12:09.675）の 1.1 秒後に受信 |

- **解釈:** 停止中の削除も拾う。遅延は周期に依存する

### 4.12 run13: 3 経路と決定的な id {#run13}

- **目的:** 3 つの経路から同じ id が届くか、adapter を止めたときにどの経路が拾うかを確かめる（Q2・Q4）
- **手順:** 次の 3 経路を、同じ Broker に向けて同時に動かした。
  - ApiServerSource（EventTransform で id を `<uid>:deleted` にする）
  - 自前 finalizer
  - PingSource による突き合わせ
- **結果:**

| 場面 | 経路 | 受信 |
|---|---|---|
| 通常（消滅 09:23:59.776） | finalizer | 09:23:59.731 |
| | ApiServerSource | 09:23:59.789 |
| | 突き合わせ | 09:24:00.222 |
| adapter 停止（消滅 09:26:41.826） | finalizer | 09:26:41.740 |
| | 突き合わせ | 09:27:00.159 |
| | ApiServerSource | 届かず |

id は、どの経路でも `<uid>:deleted` だった。team-a の Broker にも、同じ件数だけ転送された。

- **解釈:** 経路が違っても id は同じになる。adapter が止まっていると、ApiServerSource だけが取りこぼす

### 4.13 run14: Namespace を消す Job を改修する案（採らない案の検証） {#run14}

- **目的:** Job が消滅を待ってから送る形の動きを確かめる（Q7）
- **手順:** 12 行のスクリプトで、`delete` → `kubectl wait --for=delete` → Broker に POST、を行った。次の 3 つを試した。
  - A: 通常
  - B: Terminating のまま止まる（ConfigMap の finalizer）。タイムアウトは 20 秒
  - C: すでに消えている Namespace
- **結果:**

| 場面 | 結果 |
|---|---|
| A | 受信 09:29:15.968。Job 完了 09:29:18.496。id は `ns:nsa:deleted:<Job の uid>` |
| B | Pod が 4 回失敗し、`BackoffLimitExceeded` で Failed。通知は無し |
| C | Job 完了（09:32:00.889）、受信 09:31:57.684 |

- **解釈:** 動くが、基盤の Job に通知の都合を持ち込むので採らない。止まった場合は Job の失敗として見える

### 4.14 run15: Namespace の観測 {#run15}

- **目的:** Namespace の DELETE がいつ出るか、selector が効くか、取りこぼしの条件を確かめる（Q2・Q7）
- **手順:** ラベル付きの Namespace を見る ApiServerSource と、突き合わせ（ADD も記録）を動かして、次の 4 つを試した。
  - A: ラベル付きの Namespace と、ラベルの無い Namespace を削除する
  - B: adapter を止めて削除する
  - C: 1 周期の中で作って消す
  - D: adapter を止めたまま作って消す
- **結果:**

| 場面 | 受信 |
|---|---|
| A（消滅 09:35:38.243） | update ×2（09:35:27.857・09:35:32.868、Terminating）、ApiServerSource の delete 09:35:38.144、突き合わせ 09:36:00.371。ラベルの無い Namespace は届かなかった |
| B（消滅 09:38:23.778） | 突き合わせ 09:39:00.353 のみ |
| C（消滅 09:40:08.519） | ApiServerSource 09:40:08.525、突き合わせ 09:41:00.285 |
| D | 0 件 |

- **解釈:** Terminating は UPDATE、DELETE は完全に消えた時点で出る。ADD を記録すれば、短命な Namespace も拾える。adapter が生存期間中ずっと止まっていると、どちらの経路でも取れない

### 4.15 run16: 宛先の障害は削除を止めない {#run16}

- **目的:** アプリ側の宛先が失敗しても、削除が止まらないかを確かめる（Q3）
- **手順:** team-a の Trigger の宛先を常に 500 にして、Application を削除した
- **結果:**
  - 削除は 09:44:07.278 に始まり、消滅は 09:44:18.688 だった。
  - finalizer 経路のイベントは、4 回試行（09:44:15.135〜09:44:18.646）したあと DLQ に入った（09:44:18.648）。
  - ApiServerSource 経路のイベントも、同じく 4 回試行したあと DLQ に入った（09:44:22.211）。
- **解釈:** 宛先の障害は Broker の先で閉じ、削除は止まらない

### 4.16 run17: Namespace をマニフェストに含む Application {#run17}

- **目的:** Argo CD が Namespace の消滅まで Application を残すかを確かめる（削除完了の定義）
- **手順:** Namespace と、finalizer 付きの ConfigMap を含むチャートを削除した。ConfigMap の finalizer は後から外した
- **結果:**
  - 削除（09:49:11）の直後から、Application は `resources-finalizer` を 1 つ残し、Namespace は Terminating で止まった。
  - finalizer を外すと（09:49:58）、どちらも 09:50:03 までに消えた。
  - 数字は画面出力から取った。ログは保存していない。
- **解釈:** Argo CD は、管理している Namespace が消えるまで Application を残す

### 4.17 run18: 自前の informer の再起動 {#run18}

- **目的:** client-go の informer は、プロセスを再起動したあと、止まっていた間の削除を出すかを確かめる（Q2）
- **手順:** client-go v0.35.7 の 39 行の watcher を起動して止め、その間に Namespace を消し、再起動した
- **結果:** 1 回目の起動では `ADD nsw`（09:50:59.459）。再起動後の出力は空だった
- **解釈:** キャッシュはメモリにしかないので、再起動をはさむと削除は届かない

### 4.18 run19: Application の観測によるデプロイ完了 {#run19}

- **目的:** 基盤側の設定を触らずに、Notifications の `on-deployed` と同じ条件でデプロイ完了を取れるかを確かめる（Q4・Q6）
- **手順:**
  - ApiServerSource で Application を watch する。観測 Service（41 行）が、カタログと同じ条件で `<uid>:<revision>:deployed` を送る。PingSource で毎分の突き合わせも行った。
  - Notifications も、同じ条件で並べて動かした。
  - 0.1.0 で作成したあと 0.2.0 に上げ（run19c）、0.1.0 に戻し、adapter を止めた状態で 0.2.0 に上げた（run19d）。
  - revision の変更は、Helm リポジトリのキャッシュのため、hard refresh を付けないと反映されなかった。run19 と run19c の途中はこれで時間切れになったので、その区間の数字は使わない。
- **結果:**

| 場面 | Notifications | 観測（ApiServerSource） | 観測（突き合わせ） |
|---|---|---|---|
| 0.1.0 作成（run19c、OBSERVED 15:20:16.925） | 15:20:16.299 に 1 通 | 15:20:16.290 から 4 通（同じ id） | 毎分 1 通 |
| 0.1.0 に戻す（run19d、OBSERVED 15:31:22.285） | 送らなかった（`already sent`） | 15:31:22.308 から 2 通 | 15:32:00.513 に 1 通 |
| adapter を止めて 0.2.0（OBSERVED 15:32:54.582） | 送った（ログは notifications-controller 側で確認） | 届かず | 15:33:00.503（+5.9 s） |

- **解釈:**
  - 初回のデプロイ完了は、Notifications と観測 Service がほぼ同時に出した（差は 9 ms）。
  - 同じ revision に戻すと、Notifications は `oncePer` で黙り、観測 Service は前と同じ id を出した。受け手が id で重複を消すと、ロールバックが消えるので、id に operation の開始時刻を足す必要がある。
  - adapter の停止中のデプロイは、突き合わせが拾った。

### 4.19 基盤の負荷の計測（footprint） {#footprint}

kind に各部品を順に入れ、そのつど CRD・ワークロード・ClusterRole の数を数えて、前の状態との差を取った（`runs/footprint/*`）。結果は[推奨構成の詳細](recommended.html#footprint)の表のとおり。

## 5. まとめ: 問いと run の対応

| 問い | 確かめた run | 答え | 未確認の部分 |
|---|---|---|---|
| Q1 削除の開始と完了 | run3・run6 | 区別できる。完了を取れるのは watch 系と finalizer | — |
| Q2 停止中の削除 | run4・run5・run12・run13・run15・run18 | watch 系は取りこぼす。突き合わせと finalizer は拾う | 410 Gone による再 list（実測していない） |
| Q3 retry・DLQ | run8・run10・run16 | Knative は宣言どおり。Notifications は 4 回試行して終わり | Kafka・RabbitMQ・NATS の土台 |
| Q4 重複 | run3・run13・run19 | 決定的な id で消せる。ロールバックでは id が衝突する | — |
| Q5 権限・越境 | run9・run11・run12 | 覗けない。偽装は既定では防げない | EventPolicy（OIDC）での防御 |
| Q6 デプロイ完了を観測で取る | run7・run19 | 取れる。Notifications と同じ条件で揃った | 複数モジュールの集約 |
| Q7 Namespace の消滅を観測で取る | run14・run15・run17 | 取れる。Terminating と消滅を区別できる | — |
| Q8 HA | run11 | Metacontroller はリーダーが変わっても取りこぼさなかった | ApiServerSource の adapter の HA（2 台だと 2 通になることは確認） |

## 6. 制約と未確認事項

- **環境:** kind の 1 ノードで測った。Kubernetes は 1.33.1 で、Knative v1.23.0 は 1.34 以上を要求するため、起動時の検査を外した。
- **Broker:** 永続化しない InMemoryChannel で測った。Kafka・RabbitMQ・NATS JetStream の保証は、文献だけに基づく。
- **HA:** 複数ノード、ノード障害、ネットワークの分断は試していない。Argo Events、Notifications、ApiServerSource の adapter の HA は確かめていない。
- **410 Gone:** watch が期限切れになったときの再 list による取りこぼしは、ソースからの推論にとどまる。
- **ログの欠落:** run2 はセッションが途切れたので使わない。run8 の一部、run11、run17 は、数字を画面出力から取った（ログを保存していない）。
- **時計:** ホストと Pod の時計のずれは測っていない。
