# Argo CD Application の完了通知

> Argo CD の `Application` について、デプロイ完了（Synced かつ Healthy）と削除完了（finalizer の処理が終わってオブジェクトと管理リソースが実際に消えた時点）を検知し、外部へ送る 6 つの方式を比べる。根拠は kind 上の Argo CD v3.5.3 での実測と、各プロジェクトのソース・公式ドキュメント。方式ごとの詳細は各ページに分けた。

## 結論

**検知と配送を分けて組む。検知は「確実に取る」役と「速く取る」役に分け、配送は永続化した Broker に任せる。**

| 役割 | 何を使うか | 理由 |
|---|---|---|
| デプロイ完了の検知 | Argo CD Notifications の `on-deployed` | 1 リビジョンにつき 1 回だけ届いた。送信済みの記録を Application の annotation に持つので、再起動しても二重に送らない |
| 削除完了の検知（確実） | 自前 finalizer のコントローラ | Argo CD の finalizer が全部外れて自分の finalizer だけが残ったら送り、成功してから外す。通知系を全部止めたまま削除しても、復旧後に届いたのはこれだけだった |
| 削除完了の検知（速報、任意） | Knative ApiServerSource の delete | 消滅から 5 ms で届く。ただし止まっている間の削除は取りこぼすので、速報としてだけ使い、確実な通知は上の finalizer に任せる |
| 配送 | Knative Broker / Trigger（Kafka Broker などの永続化した実装） | retry・backoff・DLQ を Trigger ごとに宣言できる（実測済み）。送信先を足すときは Trigger を 1 枚足すだけで、送る側に手を入れない |

**`on-deleted` は削除完了ではない。** 条件が `deletionTimestamp != nil` なので、削除要求から 0.06 秒後、まだ何も消えていない時点で発火する。

**watch で DELETE を拾う方式（Knative / Argo Events / API stream）に共通の弱点は、検知層での取りこぼし。** 受け手が止まっている間に消えた Application の DELETE は、復旧後も届かなかった。これは Kubernetes の watch と informer の性質によるもので、特定の製品に固有の欠点ではない。配送層の強さは製品ごとに大きく違い、Knative の配送層は 6 方式の中で最も強い。

```diagram
title: 推奨構成
caption: 推奨構成。検知（確実・速報）→ 配送（Broker）→ 送信先
height: 440
zones:
  - {label: "argocd namespace（Platform）", kind: platform, box: [10, 30, 300, 380]}
  - {label: "notify namespace（Platform）", kind: platform, box: [330, 30, 330, 380]}
  - {label: "App チームの namespace / 外部", kind: app, box: [680, 30, 310, 380]}
nodes:
  - {id: app, kind: app, label: "Application", mono: ["finalizers: argocd の 3 つ", "+ notify.example.com/deletion", "annotation: notified.…"], box: [25, 60, 270, 76]}
  - {id: ncc, label: "notifications-controller", lines: ["trigger: on-deployed"], mono: ["template で CloudEvent を組む"], box: [25, 200, 270, 70]}
  - {id: fin, label: "notify-finalizer（自前）", lines: ["残りが自分だけ → 送信 → 外す"], mono: ["2 レプリカ + Lease"], box: [345, 60, 300, 70]}
  - {id: src, label: "ApiServerSource（速報、任意）", lines: ["resource.delete"], box: [345, 160, 300, 54]}
  - {id: brk, kind: state, label: "Broker（Kafka Broker など）", lines: ["永続化・retry・DLQ"], mono: ["delivery: retry / backoff / DLQ"], box: [345, 250, 300, 70]}
  - {id: dlq, label: "DLQ", mono: ["配送できなかったイベント"], box: [345, 345, 300, 50]}
  - {id: t1, kind: ext, label: "Trigger → Slack 送信", mono: ["filter: type=…deployed"], box: [695, 60, 280, 52]}
  - {id: t2, kind: ext, label: "Trigger → 社内 API 送信", mono: ["filter: type=…deleted"], box: [695, 170, 280, 52]}
  - {id: t3, kind: ext, label: "Trigger → 追加の送信先", mono: ["Trigger を 1 枚足すだけ"], box: [695, 280, 280, 52]}
edges:
  - {from: ncc, to: app, kind: watch, label: watch, dx: 30}
  - {from: fin, to: app, kind: watch, via: [[330, 80]]}
  - {from: fin, to: app, kind: patch, via: [[330, 115]], label: "finalizer", dy: 16}
  - {from: src, to: app, kind: watch, via: [[330, 187], [300, 187]]}
  - {from: ncc, to: brk, kind: ce, via: [[320, 285]], label: "…app.deployed", dy: -6}
  - {from: fin, to: brk, kind: ce, via: [[620, 150], [620, 245]], label: "…app.deleted", dx: -38}
  - {from: src, to: brk, kind: ce}
  - {from: brk, to: dlq, kind: ce}
  - {from: brk, to: t1, kind: ce}
  - {from: brk, to: t2, kind: ce}
  - {from: brk, to: t3, kind: ce}
```

組むときの注意:

- **自前 finalizer は、作成時点で付いていないと効かない。** コントローラが止まっている間に作られて消えた Application は取りこぼす。確実に付けたいなら admission で足す（Kyverno の mutate ポリシーなど。この部分は実測していない）
- **コントローラが止まっている間、削除は完了しない。** 自前の finalizer が残るので Application は消えずに待つ（実測で確認）。削除できるかどうかをこのコントローラに預けることになるので、2 レプリカ以上とリーダー選出が要る
- **非カスケード削除（`resources-finalizer.argocd.argoproj.io` が付いていない）では、削除開始の直後に送る。** 管理リソースを消さない削除なので仕様どおりの動きになる。ペイロードにカスケードかどうかを入れておき、受け手で区別する
- **速報と確実な通知は同じ削除で 2 通届く。** CloudEvent の `type` を分けておき、受け手は Application の `uid` を冪等キーにする

Knative が無い環境なら、Broker を挟まず両コンポーネントから直接 HTTP で送っても組める。その場合、配送層の retry は送信側の実装（Notifications は 4 回試行して諦める）に頼ることになり、DLQ は無い。

---

## 方式

<div class="pagegrid">
<a class="pcard" href="notifications.html"><b>① Argo CD Notifications</b><span>trigger の条件式を評価し、service で送る。Argo CD に同梱</span></a>
<a class="pcard" href="hooks.html"><b>② PostSync / PostDelete Job</b><span>application-controller が hook の Job を実行する</span></a>
<a class="pcard" href="knative.html"><b>③ Knative Eventing</b><span>ApiServerSource → Broker / Trigger。CloudEvents で運ぶ</span></a>
<a class="pcard" href="argo-events.html"><b>④ Argo Events</b><span>resource EventSource → EventBus → Sensor</span></a>
<a class="pcard" href="finalizer.html"><b>⑤ 自前 finalizer コントローラ</b><span>自分の finalizer を付け、最後の 1 つになったら送る</span></a>
<a class="pcard" href="api-stream.html"><b>⑥ Argo CD API stream</b><span>/api/v1/stream/applications を購読する常駐クライアント</span></a>
</div>

①〜③ は依頼で必須とされた方式、④〜⑥ は追加の提案。

### 追加提案の選定基準

候補を 3 つの条件で絞った。数字は 2026-09-25 に GitHub API（`gh api`）で取った値。

1. 削除完了のシグナル（watch の DELETE か、自分の finalizer）を自力で受けられる。admission で受ける DELETE は削除開始の時点なので対象外
2. 直近 180 日以内に push がある
3. クラスタの中で閉じてセルフホストできる

| 候補 | star | 直近 push | 最新リリース | 判定 |
|---|---:|---|---|---|
| Argo Events | 2,694 | 2026-09-20 | v1.9.11（2026-07-13） | 採用（④） |
| controller-runtime（自前コントローラの土台） | 2,960 | 2026-09-25 | v0.25.1（2026-09-14） | 採用（⑤） |
| Argo CD API server の stream（Argo CD 本体） | 24,240 | 2026-09-25 | v3.5.3（2026-09-14） | 採用（⑥） |
| Kyverno | 8,178 | 2026-09-25 | v1.19.1（2026-09-10） | 条件 1 を満たさない。⑤ の finalizer を作成時に付ける補助にだけ使える |
| Robusta | 3,101 | 2026-09-24 | 0.50.0（2026-09-16） | 条件 1 を確認できなかった（kubewatch 経由で任意の CRD を監視できるか、ドキュメントで確かめられなかった） |
| Botkube | 2,310 | 2024-12-11 | v1.14.0（2024-11-13） | 条件 2 を満たさない |
| Tekton Triggers | 594 | 2026-09-24 | v0.37.1（2026-09-23） | 条件 1 を満たさない（Kubernetes の watch を自分では持たない） |

必須方式の本体の数字は、Knative Eventing が 1,554 star・v1.23.0（2026-07-28）、notifications-engine が 335 star（リリースは無く、Argo CD がコミット固定で取り込んでいる）。

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
  <text x="20" y="184">⑤ 自前 finalizer</text><circle class="mk-ok" cx="935" cy="180" r="6"/><text class="t-mono" x="700" y="184">残り finalizer が自分だけ →</text>
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
<tr><td><a href="finalizer.html">⑤ 自前 finalizer</a></td><td>◎ 消滅を保証</td><td>◎ 復旧後に拾う</td><td>○ 自前（成功まで外さない）</td><td>◎ at-least-once＋uid</td><td>× 止まると削除も止まる</td><td>○ Broker に出せば ◎</td><td>△ 単一リーダー</td><td>○ 自前で OTel</td><td>△ applications の patch</td><td>△ 自作コード</td><td>○ 45 ms 前に送信</td></tr>
<tr><td><a href="api-stream.html">⑥ API stream</a></td><td>○ DELETED</td><td>× 取りこぼす</td><td>× 無い</td><td>× 詰まると捨てる</td><td>△ 自前</td><td>△ 自前</td><td>△ 自前</td><td>△ 自前</td><td>○ Argo CD の RBAC で絞られる</td><td>× 自作</td><td>◎ 2 ms</td></tr>
</tbody>
</table>
</div>

採点の根拠は各方式のページに書いた。表を縦に読むと、watch 系（③④⑥）は検知層が全部 × で、違いが出るのは配送層から後になる。自前 finalizer（⑤）はその逆で、検知層は ◎ だが、可用性と運用負荷を自分で背負う。推奨構成はこの 2 つを組み合わせて、互いの × を埋めている。

---

## 実測の条件と記録

kind v0.29.0（Kubernetes v1.33.1）の単一ノードに、各プロジェクトの最新リリースを入れて測った。

| 構成要素 | 版 | 備考 |
|---|---|---|
| Argo CD | v3.5.3 | 公式の `install.yaml`。Notifications の trigger と template は `argocd-notifications-cm` に書いた |
| Knative Eventing | v1.23.0 | core・InMemoryChannel・MT channel broker。v1.23.0 は Kubernetes 1.34 以上を要求するので、`KUBERNETES_MIN_VERSION=1.33.0` で検査を外した。Knative Serving は入れず、Trigger の宛先には通常の Service を使った。Kafka Broker は入れていない |
| Argo Events | v1.9.11 | EventBus は JetStream（3 レプリカ） |
| 自前 finalizer | 試作 | Python で、1 秒ごとに全件を見直す |

テスト用の Application は、クラスタ内の Helm リポジトリに置いたチャート（ConfigMap・Deployment・PostSync Job・PostDelete Job）を、`resources-finalizer.argocd.argoproj.io` 付き・自動 sync でデプロイするもの。受け手は 1 つの Pod で、受け取った時刻とヘッダを記録した。

| run | 内容 | 結果 |
|---|---|---|
| run3 | 全方式を動かしたまま作成し、削除 | ライフサイクル図の時刻はこの run の値。Notifications の deployed は 1 回、Argo Events の deployed は 4 回、Knative の update は作成で 14 回届いた |
| run4 | 自前 finalizer を付けたうえで、通知系を全部止めて削除し、25 秒後に復旧 | Application は自前 finalizer を 1 つ残して待った。復旧後に自前コントローラが送り、Knative もオブジェクトがまだ残っていたので delete を送った。Notifications と Argo Events は何も送らなかった |
| run5 | 自前 finalizer なしで、全部止めて削除し、消滅後に復旧 | 届いたのは PostDelete hook だけ。ほかは 90 秒待っても何も送らなかった |
| run6 | Notifications にカスタム trigger（`deletionTimestamp` かつ health が Missing）を足して削除 | 管理リソースが消えた直後に発火した。自前コントローラは、消滅の 45 ms 前に送った |
| run7 | Notifications から CloudEvent を組んで Knative Broker に POST | Trigger の `type` フィルタを通って届いた |
| run8 | 宛先を常に 500 を返すようにして、各方式の retry と DLQ を確かめた | Knative: 初回＋retry 3 回（0.5 → 1 → 2 秒）のあと DLQ へ。`Ce-Knativeerrorcode: 500` などが付き、`Ce-Id` は初回と同じだった。Argo Events: `policy.status.allow` を指定すると retry 3 回のあと `dlqTrigger` へ（指定しないと 500 でも成功扱いになり、1 回で終わった）。Notifications: 4 回試行（1 → 2 → 4 秒）で諦め、annotation には送信済みとして記録され、以後は送り直されなかった |
| run9 | App チーム用の namespace `team-a` を作り、`edit` と Knative の namespaced-admin を与えて、テナント越境を試した | ApiServerSource は作れたが、SubjectAccessReview で `argocd` namespace の applications を見る権限が無いと判定され、Ready にならなかった。Platform の Broker には、team-a の Pod から偽の delete イベントを POST でき、Platform の受け手まで届いた（EventPolicy を設定していない既定の状態）。argocd namespace の applications と secrets には、どちらも手が届かなかった |

**確かめていないこと:**

- 複数レプリカ構成でのフェイルオーバー
- Knative のトレースを有効にしたとき、`traceparent` が受け手まで伝わるか
- Kafka Broker での永続化と順序
- EventPolicy を有効にしたときに偽装を防げるか
- Kyverno で作成時に finalizer を付ける構成
- Robusta が CRD の削除を拾えるか

どれも実測はしていない。文献で書いてある内容は文献ベースと明記し、それ以外は評価に使っていない。
