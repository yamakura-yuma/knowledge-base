# Argo CD Application の完了通知

> Argo CD の `Application` について、デプロイ完了（Synced かつ Healthy）と削除完了（finalizer の処理が終わってオブジェクトと管理リソースが実際に消えた時点）を検知し、外部へ送る 6 つの方式を比べる。根拠は kind 上の Argo CD v3.5.3 での実測と、各プロジェクトのソース・公式ドキュメント。方式ごとの詳細は各ページに分けた。

## 結論: おすすめ

**おすすめは次の構成。**

- **デプロイ完了:** Argo CD Notifications の `on-deployed` で取る。
- **削除完了:** Metacontroller の DecoratorController で Application に finalizer を付け、finalize hook で取る。hook の中身は、Argo CD の finalizer が全部外れたら送信先に HTTP で送るだけの Webhook。
- **Broker:** 必須ではない。送信先が 1〜2 か所のうちは、直接送ればよい。

おすすめの理由:

1. **削除完了を取りこぼさないのは、finalizer 方式だけ。**
   - Notifications の `on-deleted` は削除**開始**で発火する。watch 系（Knative ApiServerSource、Argo Events、API stream）は、止まっている間に起きた削除を取りこぼす。
   - finalizer 方式では、Metacontroller を止めたまま削除しても Application は消えずに待ち、復旧後に通知が届いた（run10）。
2. **自前のコントローラは書かない。** finalizer の付け外し、watch、再同期、リーダー選出は Metacontroller が持つ。自分で書くのは、状態を持たない Webhook 1 つ（試作で約 30 行）。
   - これを controller-runtime で自作しても、得るものは少ない。検知の確実さも、配送保証も変わらない。増えるのは保守するコードだけ。
3. **Broker が無くても、配送保証は落ちない。** finalize hook が送信に失敗すると「まだ終わっていない」と返す。すると Metacontroller が hook を呼び直すので、送信先が戻るまで何度でも再送される（run10 で実測）。
   - 状態は Application の finalizer 自身が持つ。永続チャネルは要らない。
   - 代わりに、送信先が長く落ちていると削除も完了しない。

### Broker は必須か {#broker}

**必須ではない。** Broker が効くのは、「送信先が増える」「送信先ごとに再送と DLQ を分けたい」ときだけ。

| 構成 | 向いている状況 | 配送保証 | 送信先が落ちたとき |
|---|---|---|---|
| **直接送る（おすすめの起点）**: finalize hook と Notifications が送信先へ HTTP で送る | 送信先が 1〜2 か所。Knative を入れていない | 削除: at-least-once（送れるまで finalizer を外さない）<br>デプロイ: Notifications は 4 回試して諦める | 削除は送れるまで待つ（削除が止まる）。デプロイ通知は失われる |
| **Knative Broker を挟む** | 送信先が 3 か所以上、または複数チーム。送信先ごとに再送・DLQ を変えたい | Broker が受け取った時点で hook は成功。その先は Broker の実装しだい（下の表） | 削除はすぐ完了する。再送は Broker が受け持ち、上限を超えたら DLQ へ |

Broker を挟む場合、**永続化の選択肢は Kafka だけではない。** 3 つの実装を、一次情報で比べた。

| 実装 | 何が保証されるか | 根拠 | 成熟度・数字 |
|---|---|---|---|
| **Kafka Broker**（`knative-extensions/eventing-kafka-broker`） | Kafka の topic に書く。replication factor を設定できる。制御面の HA、データプレーンの水平スケール。`delivery.order: ordered` でパーティション単位の順序 | [Kafka Broker のドキュメント](https://github.com/knative/docs/blob/main/docs/versioned/eventing/brokers/broker-types/kafka-broker/README.md) | 201 star、knative-v1.23.1（2026-08-25） |
| **RabbitMQ Broker**（`knative-extensions/eventing-rabbitmq`） | exchange と queue は `Durable: true`、メッセージは `DeliveryMode: Persistent`。ingress は publisher confirm（`PublishWithDeferredConfirm` と `Wait()`）で RabbitMQ の ack を待ち、nack なら 500 を返す。`queueType: quorum` を指定できる。Trigger の既定の並列度は 1 で、順序を保つ。delivery spec が無いと、最初の失敗で NACK して**捨てる** | [RabbitMQ Broker の README](https://github.com/knative-extensions/eventing-rabbitmq/blob/main/docs/broker/README.md)、`pkg/rabbit/queue.go`・`message.go`、`cmd/ingress/main.go` | 100 star、knative-v1.23.0（2026-07-28） |
| **NATS JetStream Channel**（`knative-extensions/eventing-natss`） | stream の storage は既定で File、クラスタなら replicas を指定できる。consumer は `AckExplicitPolicy`。失敗したら `NakWithDelay` で遅らせて再配送する。publish のとき CloudEvent の ID を `MsgId` に入れるので、`duplicateWindow` の間は同じ ID の重複を JetStream が除く | [docs/jetstream.md](https://github.com/knative-extensions/eventing-natss/blob/main/docs/jetstream.md)、`pkg/channel/jetstream/dispatcher/` | 48 star、knative-v1.23.2（2026-09-01）。README に "These components are BETA"。JetStream Broker の文書（at-least-once を謳う）は 2026-09-21 に追加されたばかり |

3 つとも、Trigger の `delivery`（retry・backoff・deadLetterSink）に対応している。どれも実測していない。今回の kind で測ったのは、永続化しない InMemoryChannel だけ。選ぶ基準は、どのメッセージ基盤をすでに運用しているかで決めてよい。

### 状況ごとのおすすめ

| 状況 | おすすめ | その代わりに失うもの |
|---|---|---|
| 基本形（削除完了を取りこぼせない、送信先は少ない） | **Notifications ＋ Metacontroller の finalize hook、直接送る** | 送信先が長く落ちると、削除が止まる。デプロイ通知は失敗すると失われる |
| 送信先が多い、複数チームに配る | 上の構成の送信先を **Knative Broker** にする（永続化は Kafka / RabbitMQ / NATS JetStream のうち、運用しているもの） | Knative と、メッセージ基盤の運用 |
| 削除は「管理リソースが消えた」で十分。部品を増やしたくない | Notifications だけで組む。`on-deployed` と、カスタム trigger（`deletionTimestamp != nil and health == Missing`） | CR が消えた保証、止まっている間の削除、失敗時の再送 |
| Argo Events をすでに運用している | 配送を Argo Events に任せ、削除完了は Metacontroller で取る。`atLeastOnce: true` と `policy.status.allow` は必ず指定する | CloudEvents と OTel の連携 |

**避けたほうがよいもの:**

- `on-deleted` を削除完了として扱う。削除要求から 0.06 秒後、まだ何も消えていない時点で発火する。
- PostDelete hook だけに任せる。送信先が落ちていると、削除そのものが詰まり、アプリごとに Job を書くことになる。
- API stream を常駐させる。受け取りが詰まると、イベントを捨てる。
- finalizer のコントローラを一から自作する。Metacontroller で足りる。

```diagram
title: 推奨構成
caption: 推奨構成（直接送る形）。送信先が増えたら、点線の Broker を挟む
height: 400
zones:
  - {label: "argocd namespace（基盤）", kind: platform, box: [10, 30, 300, 330]}
  - {label: "metacontroller / notify（基盤）", kind: platform, box: [330, 30, 330, 330]}
  - {label: "送信先（利用者）", kind: app, box: [680, 30, 310, 330]}
nodes:
  - {id: app, kind: app, label: "Application", mono: ["finalizers: argocd の 3 つ", "+ metacontroller.io/…", "annotation: notified.…"], box: [25, 60, 270, 76]}
  - {id: ncc, label: "notifications-controller", lines: ["trigger: on-deployed"], mono: ["同梱・設定だけ"], box: [25, 200, 270, 70]}
  - {id: mc, label: "Metacontroller", lines: ["DecoratorController"], mono: ["finalizer の付け外し・再試行"], box: [345, 60, 300, 70]}
  - {id: hook, label: "finalize hook（Webhook）", lines: ["残りが自分だけ → 送信"], mono: ["状態なし・2 レプリカ"], box: [345, 170, 300, 70]}
  - {id: brk, kind: crd, label: "Knative Broker（任意）", mono: ["送信先が増えたら挟む"], box: [345, 280, 300, 54]}
  - {id: t1, kind: ext, label: "Slack", box: [695, 60, 280, 44]}
  - {id: t2, kind: ext, label: "社内 API", mono: ["uid で冪等に受ける"], box: [695, 170, 280, 54]}
edges:
  - {from: ncc, to: app, kind: watch, label: watch}
  - {from: mc, to: app, kind: patch, via: [[320, 97]], label: "finalizer", dy: -6}
  - {from: mc, to: hook, kind: http, label: "finalize"}
  - {from: ncc, to: t1, kind: http, via: [[320, 250], [320, 20], [835, 20]], label: "deployed", dx: 100}
  - {from: hook, to: t2, kind: http, label: "deleted（CloudEvent）"}
  - {from: hook, to: brk, kind: ce}
```

組むときの注意:

- **Metacontroller の finalizer は、作成時点で付いていないと効かない。** Metacontroller が止まっている間に作られ、そのまま消えた Application は取りこぼす。
- **Metacontroller が止まっている間、削除は完了しない。** 実測で確認した（run10）。`--leader-election` を付けて 2 レプリカ以上で動かす。
- **非カスケード削除では、削除開始の直後に送る。** `resources-finalizer.argocd.argoproj.io` が付いていないと、Argo CD は管理リソースを消さずに finalizer をすぐ外すため。ペイロードにカスケードの有無を入れ、受け手で区別する。
- **受け手は Application の `uid` で冪等にする。** finalize hook は、送信に成功してから `finalized: true` を返す。その応答の前に落ちると、同じ削除を 2 回送る。

---

## グラレコ

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
    <text class="gr-m" x="148" y="54">消えた！…を</text>
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
    <text class="gr-m" x="140" y="142">watch は寝ている間の DELETE を見逃す</text>
    <text class="gr-s" x="140" y="164">Knative / Argo Events / API stream 共通</text>
  </g>

  <path class="gr-sep" d="M30,300 C300,292 700,308 970,298"/>

  <!-- 3. 鍵: finalizer = 消えない約束 -->
  <g transform="translate(40,330)">
    <text class="gr-h" x="0" y="0">ひらめき：finalizer は「消えない約束」</text>
    <!-- 錠前 -->
    <rect class="gr-lock" x="10" y="40" width="80" height="64" rx="8"/>
    <path class="gr-line2" d="M26,40 v-14 a24,24 0 0 1 48,0 v14"/>
    <circle class="gr-dot" cx="50" cy="70" r="7"/>
    <text class="gr-m" x="110" y="52">自分の finalizer が残っている限り</text>
    <text class="gr-m" x="110" y="76">Application は消えずに待ってくれる</text>
    <text class="gr-s" x="110" y="100">→ 送れたら外す。止まっていても、起きたら続きから</text>
    <!-- 付箋: Metacontroller -->
    <g transform="translate(470,20) rotate(-3)">
      <rect class="gr-note" x="0" y="0" width="256" height="96" rx="4"/>
      <text class="gr-h" x="14" y="28">自作しない！</text>
      <text class="gr-s" x="14" y="52">Metacontroller が付け外しと再試行</text>
      <text class="gr-s" x="14" y="72">書くのは Webhook 1 つ（約 30 行）</text>
    </g>
    <g transform="translate(750,26) rotate(2)">
      <rect class="gr-note2" x="0" y="0" width="200" height="90" rx="4"/>
      <text class="gr-h" x="14" y="28">Broker は任意</text>
      <text class="gr-s" x="14" y="52">送信先が増えたら挟む</text>
      <text class="gr-s" x="14" y="72">Kafka / RabbitMQ / NATS</text>
    </g>
  </g>

  <path class="gr-sep" d="M30,470 C300,478 700,462 970,472"/>

  <!-- 4. おすすめの流れ -->
  <text class="gr-h" x="40" y="505">おすすめの流れ</text>
  <g transform="translate(40,525)">
    <ellipse class="gr-pill" cx="95" cy="40" rx="95" ry="36"/>
    <text class="gr-m" x="95" y="36" text-anchor="middle">デプロイ完了</text>
    <text class="gr-s" x="95" y="56" text-anchor="middle">Notifications</text>
    <ellipse class="gr-pill" cx="95" cy="135" rx="95" ry="36"/>
    <text class="gr-m" x="95" y="131" text-anchor="middle">削除完了</text>
    <text class="gr-s" x="95" y="151" text-anchor="middle">Metacontroller hook</text>
    <path class="gr-arrow" d="M195,45 C290,40 330,80 400,85" marker-end="url(#gr-ar)"/>
    <path class="gr-arrow" d="M195,130 C290,135 330,100 400,95" marker-end="url(#gr-ar)"/>
    <rect class="gr-env" x="410" y="55" width="190" height="70" rx="10"/>
    <path class="gr-line" d="M410,58 L505,100 L600,58"/>
    <text class="gr-s" x="505" y="146" text-anchor="middle">HTTP + CloudEvents</text>
    <text class="gr-s" x="505" y="164" text-anchor="middle">ID = uid で重複を除く</text>
    <path class="gr-arrow" d="M605,90 C680,70 720,40 780,40" marker-end="url(#gr-ar)"/>
    <path class="gr-arrow" d="M605,95 C680,110 720,140 780,140" marker-end="url(#gr-ar)"/>
    <text class="gr-m" x="790" y="45">Slack</text>
    <text class="gr-m" x="790" y="145">社内 API</text>
  </g>

  <!-- 5. 役割分担 -->
  <g transform="translate(40,700)">
    <circle class="gr-head" cx="14" cy="8" r="10"/><path class="gr-line2" d="M14,18 v22 M0,28 h28"/>
    <text class="gr-m" x="40" y="22"><tspan class="gr-b">基盤チーム</tspan>：部品を入れて守る</text>
    <circle class="gr-head gr-head2" cx="534" cy="8" r="10"/><path class="gr-line2" d="M534,18 v22 M520,28 h28"/>
    <text class="gr-m" x="560" y="22"><tspan class="gr-b">利用者</tspan>：受け手を作って冪等に受けるだけ</text>
  </g>
</svg>
</div>

---

## 方式

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

## ライフサイクル上で各方式が捉える時点

時刻は実測（run3・run6）の値。削除側は `kubectl delete` を 0 秒とし、`resources-finalizer.argocd.argoproj.io` 付きで PostDelete hook を 1 つ持つ Application を消した。

<div class="dgm">
<div class="cap">デプロイ側（0 秒 = Application を作成）</div>
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
<div class="cap">削除側（0 秒 = kubectl delete）</div>
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
  <text x="20" y="212">③ Knative delete</text><circle class="mk-ok" cx="940" cy="208" r="6"/><text class="t-mono" x="790" y="212">消滅 +5ms</text>
  <text x="20" y="240">④ Argo Events DELETE</text><circle class="mk-ok" cx="940" cy="236" r="6"/><text class="t-mono" x="790" y="240">消滅 +7ms</text>
  <text x="20" y="268">⑥ API stream DELETED</text><circle class="mk-ok" cx="940" cy="264" r="6"/><text class="t-mono" x="790" y="268">消滅 +2ms</text>
  <text class="t-mono" x="20" y="292">緑: 削除完了　黄: 途中の段階　赤: 削除開始。止まっていた間の取りこぼしは別の軸（検知層の耐障害性）で評価する</text>
</svg>
</div>

Argo CD の `controller/appcontroller.go` の `finalizeApplicationDeletion` は、finalizer を 1 段ずつ外していく。
管理リソースが消え切ると `resources-finalizer.argocd.argoproj.io` を外す。
次に `post-delete-finalizer.argocd.argoproj.io` の段で PostDelete hook を実行し、成功したら外して hook を片付ける。
実測でも finalizer はこの順に外れた（`resources-finalizer` → `post-delete-finalizer` → `post-delete-finalizer/cleanup` → 消滅）。

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

## 評価マトリクス

<div class="tblwrap">
<table class="mx">
<thead><tr><th>方式</th><th>削除完了の検知</th><th>検知層の耐障害性</th><th>配送層の回復性</th><th>配送保証</th><th>可用性</th><th>疎結合・独立デプロイ</th><th>スケーラビリティ</th><th>可観測性</th><th>セキュリティ・権限分離</th><th>運用負荷</th><th>レイテンシ</th></tr></thead>
<tbody>
<tr><td><a href="notifications.html">① Notifications</a></td><td>× 削除開始</td><td>○ デプロイは拾う / 削除は×</td><td>△ 4 回試行で終わり</td><td>○ oncePer で重複除去</td><td>△ 1 レプリカ</td><td>△ cm の編集</td><td>△ 送信先ごと</td><td>△ Prometheus</td><td>○ self-service</td><td>◎ 同梱</td><td>× 削除完了なし</td></tr>
<tr><td><a href="hooks.html">② PostSync / PostDelete</a></td><td>△ CR 消滅前</td><td>◎ controller が再実行</td><td>△ backoffLimit</td><td>△ sync ごとに実行</td><td>× 失敗で削除が詰まる</td><td>× 全アプリのマニフェスト</td><td>× 自前</td><td>△ 自前</td><td>△ 資格情報がアプリごと</td><td>△ アプリごとに Job</td><td>△ 0.8 秒＋CR 消滅は後</td></tr>
<tr><td><a href="knative.html">③ Knative</a></td><td>○ DELETE</td><td>× 停止中は取りこぼす</td><td>◎ retry・backoff・DLQ</td><td>○ 永続 Broker で at-least-once</td><td>○ 制御面・Kafka 系は HA、adapter は 1</td><td>◎ Trigger を足すだけ</td><td>◎ データプレーン水平</td><td>◎ OTLP・CloudEvents</td><td>○ ns 内で完結、偽装に EventPolicy</td><td>△ 部品が多い</td><td>◎ 5 ms</td></tr>
<tr><td><a href="argo-events.html">④ Argo Events</a></td><td>○ DELETE</td><td>× 停止中は取りこぼす</td><td>○ retry・dlqTrigger</td><td>△ 既定 at-most-once</td><td>○ Active-Passive</td><td>○ Sensor の編集</td><td>○ Sensor 単位</td><td>△ Prometheus</td><td>○ ns 内で完結</td><td>△ EventBus が要る</td><td>◎ 7 ms</td></tr>
<tr><td><a href="finalizer.html">⑤ finalizer（Metacontroller）</a></td><td>◎ 消滅を保証</td><td>◎ 復旧後に拾う</td><td>○ 送れるまで呼び直す</td><td>◎ at-least-once＋uid</td><td>× 止まると削除も止まる</td><td>○ Broker に出せば ◎</td><td>△ 単一リーダー</td><td>○ hook で OTel</td><td>△ ClusterRole を絞る</td><td>○ hook 1 つ</td><td>○ 約 10 ms</td></tr>
<tr><td><a href="api-stream.html">⑥ API stream</a></td><td>○ DELETED</td><td>× 取りこぼす</td><td>× 無い</td><td>× 詰まると捨てる</td><td>△ 自前</td><td>△ 自前</td><td>△ 自前</td><td>△ 自前</td><td>○ Argo CD の RBAC で絞られる</td><td>× 自作</td><td>◎ 2 ms</td></tr>
</tbody>
</table>
</div>

採点の根拠は各方式のページに書いた。表を縦に読むと、watch 系（③④⑥）は検知層が全部 × で、違いが出るのは配送層から後になる。finalizer 方式（⑤）はその逆で、検知層は ◎ だが、可用性と運用負荷を自分で背負う。推奨構成では ⑤ で削除完了を確実に取り、配送が必要になったら ③ の配送層（Broker）だけを借りる。

---

## 実測の条件と記録

kind v0.29.0（Kubernetes v1.33.1）の単一ノードに、各プロジェクトの最新リリースを入れて測った。

| 構成要素 | 版 | 備考 |
|---|---|---|
| Argo CD | v3.5.3 | 公式の `install.yaml`。Notifications の trigger と template は `argocd-notifications-cm` に書いた |
| Knative Eventing | v1.23.0 | core・InMemoryChannel・MT channel broker。v1.23.0 は Kubernetes 1.34 以上を要求するので、`KUBERNETES_MIN_VERSION=1.33.0` で検査を外した。Knative Serving は入れず、Trigger の宛先には通常の Service を使った。Kafka Broker は入れていない |
| Argo Events | v1.9.11 | EventBus は JetStream（3 レプリカ） |
| 自前 finalizer | 試作 | Python で、1 秒ごとに全件を見直す（run4・run6） |
| Metacontroller | v4.17.2 | 公式の production マニフェスト。hook は Python で約 30 行（run10） |

テスト用の Application は、クラスタ内の Helm リポジトリに置いたチャート（ConfigMap・Deployment・PostSync Job・PostDelete Job）を、`resources-finalizer.argocd.argoproj.io` 付き・自動 sync でデプロイするもの。受け手は 1 つの Pod で、受け取った時刻とヘッダを記録した。

| run | 内容 | 結果 |
|---|---|---|
| run3 | 全方式を動かしたまま作成し、削除 | ライフサイクル図の時刻はこの run の値。Notifications の deployed は 1 回、Argo Events の deployed は 4 回、Knative の update は作成で 14 回届いた |
| run4 | 自前 finalizer を付けたうえで、通知系を全部止めて削除し、25 秒後に復旧 | Application は自前 finalizer を 1 つ残して待った。復旧後に自前コントローラが送り、Knative もオブジェクトがまだ残っていたので delete を送った。Notifications と Argo Events は何も送らなかった |
| run5 | 自前 finalizer なしで、全部止めて削除し、消滅後に復旧 | 届いたのは PostDelete hook だけ。ほかは 90 秒待っても何も送らなかった |
| run6 | Notifications にカスタム trigger（`deletionTimestamp` かつ health が Missing）を足して削除 | 管理リソースが消えた直後に発火した。自前コントローラは、消滅の 45 ms 前に送った |
| run7 | Notifications から CloudEvent を組んで Knative Broker に POST | Trigger の `type` フィルタを通って届いた |
| run8 | 宛先を常に 500 を返すようにして、各方式の retry と DLQ を確かめた | Knative: 初回＋retry 3 回（0.5 → 1 → 2 秒）のあと DLQ へ。`Ce-Knativeerrorcode: 500` などが付き、`Ce-Id` は初回と同じだった。Argo Events: `policy.status.allow` を指定すると retry 3 回のあと `dlqTrigger` へ（指定しないと 500 でも成功扱いになり、1 回で終わった）。Notifications: 4 回試行（1 → 2 → 4 秒）で諦め、annotation には送信済みとして記録され、以後は送り直されなかった |
| run10 | Metacontroller v4.17.2 の DecoratorController と finalize hook で、finalizer 方式を作り直した | Metacontroller と hook を止めたまま削除すると、Application は Metacontroller の finalizer を 1 つ残して待った。25 秒後に復旧させると、hook が送信し Application が消えた。送信先を常に 500 にすると、hook が `finalized: false` を返し続け、4 秒後・30 秒後と呼び直されて削除も待った。送信先を戻すと完了した。通常時は、送信から消滅まで約 10 ms |
| run9 | App チーム用の namespace `team-a` を作り、`edit` と Knative の namespaced-admin を与えて、テナント越境を試した | ApiServerSource は作れたが、SubjectAccessReview で `argocd` namespace の applications を見る権限が無いと判定され、Ready にならなかった。Platform の Broker には、team-a の Pod から偽の delete イベントを POST でき、Platform の受け手まで届いた（EventPolicy を設定していない既定の状態）。argocd namespace の applications と secrets には、どちらも手が届かなかった |

**確かめていないこと:**

- 複数レプリカ構成でのフェイルオーバー
- Knative のトレースを有効にしたとき、`traceparent` が受け手まで伝わるか
- Kafka Broker・RabbitMQ Broker・NATS JetStream Channel での永続化と順序（文献だけ）
- Metacontroller の複数レプリカでのフェイルオーバー
- EventPolicy を有効にしたときに偽装を防げるか
- Kyverno で作成時に finalizer を付ける構成
- Robusta が CRD の削除を拾えるか

どれも実測はしていない。文献で書いてある内容は文献ベースと明記し、それ以外は評価に使っていない。
