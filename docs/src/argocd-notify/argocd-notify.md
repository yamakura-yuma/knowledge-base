# Argo CD Application の完了通知

> Argo CD の `Application` について、デプロイ完了（Synced かつ Healthy）と削除完了（finalizer の処理が終わり、オブジェクトと管理リソースが実際に消えた時点）を検知し、外部へ送る方式の比較。kind 上の Argo CD v3.5.3 で実測した値と、各プロジェクトのソース・ドキュメントを根拠にしている。

## 結論

**デプロイ完了は Argo CD Notifications の `on-deployed`、削除完了は自前の finalizer を付ける小さなコントローラで取る。** 両者とも CloudEvents として 1 つの Broker に出し、送信先ごとの Trigger で配る。

| 何を | 何で取るか | 理由 |
|---|---|---|
| デプロイ完了 | Argo CD Notifications の `on-deployed`（カタログの条件式そのまま） | 実測で 1 リビジョンにつき 1 回だけ届いた。送信済みの記録を Application の annotation に持つので、コントローラが再起動しても重複しない |
| 削除完了 | 自前 finalizer（例 `notify.example.com/deletion`）を付け、**Argo CD の finalizer が全部外れて自分の finalizer だけが残ったとき**に送ってから外すコントローラ | 実測で、通知側を全部止めたまま削除しても、復旧後にこれだけが削除完了を届けた。送ってから finalizer を外すので at-least-once になる |
| 配送 | Knative Eventing の Broker / Trigger（永続化できるチャネルで） | 送信先の追加が Trigger 1 枚で済む。CloudEvents の属性で振り分けられる |

**`on-deleted` は削除完了ではない。** 条件は `app.metadata.deletionTimestamp != nil` で、実測では削除要求から 0.06 秒後、管理リソースが 1 つも消えていない時点で届いた。通知コントローラには削除イベントのハンドラが無いので、条件式を工夫しても「オブジェクトが消えた」瞬間は取れない（根拠は後述）。

**watch で DELETE を拾う方式（Knative ApiServerSource / Argo Events）は、タイミングは正しいが取りこぼす。** オブジェクト消滅から 5 ミリ秒以内に届いたが、受け手が止まっている間に消えた Application の DELETE は、復旧後も届かなかった。取りこぼしを許せない削除通知の一次検知には使えず、配送の経路として使う。

<div class="dgm">
<div class="cap">推奨構成</div>
<svg class="fig" viewBox="0 0 1000 330" role="img" aria-label="推奨構成の図">
  <defs><marker id="ar1" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" class="ar"/></marker></defs>
  <rect class="nd nd-app" x="20" y="120" width="150" height="70" rx="6"/>
  <text class="t-ink" x="95" y="150" text-anchor="middle">Application</text>
  <text class="t-mono" x="95" y="170" text-anchor="middle">argocd namespace</text>
  <rect class="nd" x="230" y="40" width="250" height="78" rx="6"/>
  <text class="t-ink" x="245" y="64">argocd-notifications-controller</text>
  <text x="245" y="84">trigger: on-deployed（カタログ）</text>
  <text class="t-mono" x="245" y="104">template → CloudEvent を POST</text>
  <rect class="nd" x="230" y="190" width="250" height="96" rx="6"/>
  <text class="t-ink" x="245" y="214">自前 finalizer コントローラ</text>
  <text x="245" y="234">作成時に自分の finalizer を付ける</text>
  <text x="245" y="252">残りが自分だけになったら送信</text>
  <text class="t-mono" x="245" y="272">送信成功 → finalizer を外す</text>
  <path class="ln ln-l1" d="M170,140 L228,82" marker-end="url(#ar1)"/>
  <path class="ln ln-hot" d="M170,170 L228,236" marker-end="url(#ar1)"/>
  <rect class="nd" x="540" y="110" width="160" height="90" rx="6"/>
  <text class="t-ink" x="620" y="140" text-anchor="middle">Knative Broker</text>
  <text x="620" y="160" text-anchor="middle">永続チャネル</text>
  <text class="t-mono" x="620" y="180" text-anchor="middle">例: Kafka / JetStream</text>
  <path class="ln ln-l1" d="M480,82 L538,130" marker-end="url(#ar1)"/>
  <path class="ln ln-hot" d="M480,236 L538,180" marker-end="url(#ar1)"/>
  <text class="t-mono" x="486" y="102">type=…app.deployed</text>
  <text class="t-mono" x="486" y="228">type=…app.deleted</text>
  <rect class="nd nd-out" x="770" y="30" width="210" height="52" rx="6"/>
  <text class="t-ink" x="785" y="52">Trigger → Slack 送信</text>
  <text class="t-mono" x="785" y="70">filter: type=…deployed/…deleted</text>
  <rect class="nd nd-out" x="770" y="129" width="210" height="52" rx="6"/>
  <text class="t-ink" x="785" y="151">Trigger → 社内 API 送信</text>
  <text class="t-mono" x="785" y="169">filter: type=…deleted</text>
  <rect class="nd nd-out" x="770" y="228" width="210" height="52" rx="6"/>
  <text class="t-ink" x="785" y="250">Trigger → 追加の送信先</text>
  <text class="t-mono" x="785" y="268">Trigger を 1 枚足すだけ</text>
  <path class="ln" d="M700,140 L768,58" marker-end="url(#ar1)"/>
  <path class="ln" d="M700,155 L768,155" marker-end="url(#ar1)"/>
  <path class="ln" d="M700,170 L768,252" marker-end="url(#ar1)"/>
  <text class="t-mono" x="20" y="316">青: デプロイ完了の経路　赤: 削除完了の経路　送信先の資格情報は各送信サービスの Secret に閉じる</text>
</svg>
</div>

組むうえでの注意は 3 つある。

- **finalizer を付け損ねた Application は取りこぼす。** コントローラが止まっている間に作られて消えたものが該当する。作成時点で確実に付けたいなら、admission で finalizer を足す（Kyverno の mutate ポリシーなど）。この部分は実測していない
- **コントローラが止まっている間、削除は完了しない。** 自前 finalizer が残るので Application は消えずに待つ（実測で確認）。確実さと引き換えに削除の可用性をこのコントローラに預けることになるので、2 レプリカ以上とリーダー選出が要る
- **非カスケード削除（`resources-finalizer.argocd.argoproj.io` が無い）では、削除開始の直後に送る。** 管理リソースを消さない削除なので、「Argo CD の finalizer が全部外れた」が即成り立つ。これは仕様どおりで、ペイロードにカスケードの有無を入れて受け手が区別する

Knative が入っていない環境なら、Broker を挟まずに両コンポーネントから直接 HTTP で送っても成り立つ。その場合、送信先の追加がコンポーネント側の設定変更になる。

---

## Application のライフサイクルと、各方式が捉える時点

実測（run3・run6）から時刻を取った。削除側は `kubectl delete` を発行した時刻を 0 秒とし、`resources-finalizer.argocd.argoproj.io` 付きで PostDelete hook を 1 つ持つ Application を消している。

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
  <text x="20" y="100">Notifications on-deployed</text><circle class="mk-ok" cx="910" cy="96" r="6"/><text class="t-mono" x="770" y="100">1 回だけ</text>
  <text x="20" y="130">PostSync hook（Job）</text><circle class="mk-ok" cx="580" cy="126" r="6"/><text class="t-mono" x="592" y="130">Healthy 後に実行</text>
  <text x="20" y="160">Argo Events（UPDATE+filter）</text>
  <circle class="mk-mid" cx="906" cy="156" r="5"/><circle class="mk-mid" cx="912" cy="156" r="5"/><circle class="mk-mid" cx="918" cy="156" r="5"/><circle class="mk-mid" cx="924" cy="156" r="5"/><text class="t-mono" x="770" y="160">4 回届く</text>
  <text x="20" y="190">Knative ApiServerSource</text>
  <g class="mk-mid"><circle cx="245" cy="186" r="3"/><circle cx="255" cy="186" r="3"/><circle cx="265" cy="186" r="3"/><circle cx="275" cy="186" r="3"/><circle cx="263" cy="186" r="3"/><circle cx="438" cy="186" r="3"/><circle cx="490" cy="186" r="3"/><circle cx="496" cy="186" r="3"/><circle cx="505" cy="186" r="3"/><circle cx="905" cy="186" r="3"/><circle cx="909" cy="186" r="3"/><circle cx="913" cy="186" r="3"/><circle cx="917" cy="186" r="3"/></g>
  <text class="t-mono" x="600" y="190">更新のたびに update が届く。判定は受け手側</text>
  <text x="20" y="220">API stream / 自前コントローラ</text><text class="t-mono" x="240" y="220">MODIFIED を全部受けて自分で判定する（上と同じ性質）</text>
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
  <text x="20" y="100">Notifications on-deleted</text><circle class="mk-bad" cx="246" cy="96" r="6"/><text class="t-mono t-bad" x="258" y="100">削除開始で発火（完了ではない）</text>
  <text x="20" y="128">Notifications カスタム trigger</text><circle class="mk-mid" cx="604" cy="124" r="6"/><text class="t-mono" x="400" y="128">health=Missing で発火 →</text>
  <text x="20" y="156">PostDelete hook（Job）</text><circle class="mk-mid" cx="681" cy="152" r="6"/><text class="t-mono" x="693" y="156">リソース消滅後・CR 消滅前</text>
  <text x="20" y="184">自前 finalizer コントローラ</text><circle class="mk-ok" cx="935" cy="180" r="6"/><text class="t-mono" x="700" y="184">残り finalizer が自分だけ →</text>
  <text x="20" y="212">Knative ApiServerSource delete</text><circle class="mk-ok" cx="940" cy="208" r="6"/><text class="t-mono" x="760" y="212">消滅 +5ms</text>
  <text x="20" y="240">Argo Events resource DELETE</text><circle class="mk-ok" cx="940" cy="236" r="6"/><text class="t-mono" x="760" y="240">消滅 +7ms</text>
  <text x="20" y="268">Argo CD API stream DELETED</text><circle class="mk-ok" cx="940" cy="264" r="6"/><text class="t-mono" x="760" y="268">消滅 +2ms</text>
  <text class="t-mono" x="20" y="292">緑: 削除完了を捉える　黄: 途中の段階　赤: 削除開始。停止中の取りこぼしは別（下の耐障害性を参照）</text>
</svg>
</div>

削除の段階を Argo CD のソースで確かめると、`controller/appcontroller.go` の `finalizeApplicationDeletion` が finalizer を 1 段ずつ外している。
管理リソースが残っている間は `resources-finalizer.argocd.argoproj.io` を外さず、消え切ったら外す。
次に `post-delete-finalizer.argocd.argoproj.io` の段で PostDelete hook を作って待ち、成功したら外して hook を片付ける。
実測の finalizer の推移もこの順だった（`resources-finalizer` → `post-delete-finalizer` → `post-delete-finalizer/cleanup` → 消滅）。

---

## 方式ごとのイベントフロー

<div class="dgm">
<div class="cap">Application → 検知 → 通知先</div>
<svg class="fig" viewBox="0 0 1000 420" role="img" aria-label="各方式のイベントフロー">
  <defs><marker id="ar2" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" class="ar"/></marker></defs>
  <text class="t-mono" x="20" y="18">方式</text><text class="t-mono" x="200" y="18">検知（何を見るか）</text><text class="t-mono" x="500" y="18">運び手</text><text class="t-mono" x="790" y="18">通知先</text>
  <g>
    <text class="t-ink" x="20" y="54">① Notifications</text>
    <rect class="nd" x="200" y="34" width="260" height="34" rx="5"/><text x="210" y="56">informer の Add/Update → 条件式評価</text>
    <rect class="nd" x="500" y="34" width="250" height="34" rx="5"/><text x="510" y="56">service（webhook / slack など）</text>
    <rect class="nd nd-out" x="790" y="34" width="190" height="34" rx="5"/><text x="800" y="56">Slack / Webhook</text>
    <path class="ln ln-l1" d="M460,51 L498,51" marker-end="url(#ar2)"/><path class="ln ln-l1" d="M750,51 L788,51" marker-end="url(#ar2)"/>
  </g>
  <g>
    <text class="t-ink" x="20" y="120">② PostSync /</text><text class="t-ink" x="20" y="138">PostDelete Job</text>
    <rect class="nd" x="200" y="104" width="260" height="34" rx="5"/><text x="210" y="126">app-controller が hook を実行</text>
    <rect class="nd" x="500" y="104" width="250" height="34" rx="5"/><text x="510" y="126">Job のコンテナ（curl など）</text>
    <rect class="nd nd-out" x="790" y="104" width="190" height="34" rx="5"/><text x="800" y="126">任意の HTTP</text>
    <path class="ln ln-l1" d="M460,121 L498,121" marker-end="url(#ar2)"/><path class="ln ln-l1" d="M750,121 L788,121" marker-end="url(#ar2)"/>
  </g>
  <g>
    <text class="t-ink" x="20" y="194">③ Knative</text>
    <rect class="nd" x="200" y="174" width="260" height="34" rx="5"/><text x="210" y="196">ApiServerSource（watch）</text>
    <rect class="nd" x="500" y="174" width="250" height="34" rx="5"/><text x="510" y="196">Broker → Trigger（CloudEvents）</text>
    <rect class="nd nd-out" x="790" y="174" width="190" height="34" rx="5"/><text x="800" y="196">Knative Service → 外部</text>
    <path class="ln ln-l2" d="M460,191 L498,191" marker-end="url(#ar2)"/><path class="ln ln-l2" d="M750,191 L788,191" marker-end="url(#ar2)"/>
  </g>
  <g>
    <text class="t-ink" x="20" y="264">④ Argo Events</text>
    <rect class="nd" x="200" y="244" width="260" height="34" rx="5"/><text x="210" y="266">resource EventSource（informer）</text>
    <rect class="nd" x="500" y="244" width="250" height="34" rx="5"/><text x="510" y="266">EventBus → Sensor（filter）</text>
    <rect class="nd nd-out" x="790" y="244" width="190" height="34" rx="5"/><text x="800" y="266">HTTP trigger など</text>
    <path class="ln ln-l2" d="M460,261 L498,261" marker-end="url(#ar2)"/><path class="ln ln-l2" d="M750,261 L788,261" marker-end="url(#ar2)"/>
  </g>
  <g>
    <text class="t-ink" x="20" y="334">⑤ 自前 finalizer</text>
    <rect class="nd" x="200" y="314" width="260" height="34" rx="5"/><text x="210" y="336">自分の finalizer だけ残ったか</text>
    <rect class="nd" x="500" y="314" width="250" height="34" rx="5"/><text x="510" y="336">送信 → 成功後に finalizer を外す</text>
    <rect class="nd nd-out" x="790" y="314" width="190" height="34" rx="5"/><text x="800" y="336">任意（Broker 推奨）</text>
    <path class="ln ln-l3" d="M460,331 L498,331" marker-end="url(#ar2)"/><path class="ln ln-l3" d="M750,331 L788,331" marker-end="url(#ar2)"/>
  </g>
  <g>
    <text class="t-ink" x="20" y="404">⑥ API stream</text>
    <rect class="nd" x="200" y="384" width="260" height="34" rx="5"/><text x="210" y="406">/api/v1/stream/applications</text>
    <rect class="nd" x="500" y="384" width="250" height="34" rx="5"/><text x="510" y="406">自前クライアント（常駐）</text>
    <rect class="nd nd-out" x="790" y="384" width="190" height="34" rx="5"/><text x="800" y="406">任意</text>
    <path class="ln ln-l3" d="M460,401 L498,401" marker-end="url(#ar2)"/><path class="ln ln-l3" d="M750,401 L788,401" marker-end="url(#ar2)"/>
  </g>
</svg>
</div>

①② は Argo CD の中に組み込まれた仕組み、③④ は Kubernetes の watch を汎用のイベント基盤で運ぶもの、⑤⑥ は自分で書くもの。
①〜③ は依頼で必須とされた方式、④〜⑥ は追加の提案（選定基準は次節）。

### 追加提案の選定基準

候補を次の 3 条件で絞った。値は 2026-09-25 に GitHub API（`gh api`）で取った。

1. 削除完了のシグナル（watch の DELETE か、自分の finalizer）を自力で受けられる。admission 時点の DELETE は削除開始なので外す
2. 直近 180 日以内に push がある
3. クラスタ内で閉じてセルフホストできる

| 候補 | star | 直近 push | 最新リリース | 判定 |
|---|---:|---|---|---|
| Argo Events | 2,694 | 2026-09-20 | v1.9.11（2026-07-13） | 採る（④） |
| controller-runtime（自前コントローラの土台） | 2,960 | 2026-09-25 | v0.25.1（2026-09-14） | 採る（⑤） |
| Argo CD API server の stream（Argo CD 本体） | 24,240 | 2026-09-25 | v3.5.3（2026-09-14） | 採る（⑥） |
| Kyverno | 8,178 | 2026-09-25 | v1.19.1（2026-09-10） | 条件 1 を満たさない（admission の DELETE は削除開始）。⑤の finalizer を作成時に付ける補助としてだけ使える |
| Robusta | 3,101 | 2026-09-24 | 0.50.0（2026-09-16） | 条件 1 が未確認。削除トリガ `on_kubernetes_any_resource_delete` はあるが、kubewatch 経由で任意の CRD を監視できるかはドキュメントで確かめられなかった |
| Botkube | 2,310 | 2024-12-11 | v1.14.0（2024-11-13） | 条件 2 を満たさない |
| Tekton Triggers | 594 | 2026-09-24 | v0.37.1（2026-09-23） | 条件 1 を満たさない（Kubernetes の watch を自分では持たず、別のイベント源が要る） |

参考として必須方式の本体: Knative Eventing 1,554 star・v1.23.0（2026-07-28）、notifications-engine 335 star（リリースなし、Argo CD がコミット固定で取り込む）。

---

## 評価マトリクス

<div class="tblwrap">
<table class="mx">
<thead><tr><th>方式</th><th>削除完了の検知</th><th>認証認可</th><th>API 送信</th><th>マイクロサービス適正</th><th>OTel 適正</th><th>耐障害性</th></tr></thead>
<tbody>
<tr><td><strong>① Notifications</strong></td><td><span class="g0">×</span></td><td><span class="g3">◎</span></td><td><span class="g2">○</span></td><td><span class="g1">△</span></td><td><span class="g1">△</span></td><td><span class="g1">△</span></td></tr>
<tr><td><strong>② PostSync / PostDelete Job</strong></td><td><span class="g1">△</span></td><td><span class="g1">△</span></td><td><span class="g2">○</span></td><td><span class="g1">△</span></td><td><span class="g1">△</span></td><td><span class="g2">○</span></td></tr>
<tr><td><strong>③ Knative ApiServerSource</strong></td><td><span class="g2">○</span></td><td><span class="g2">○</span></td><td><span class="g2">○</span></td><td><span class="g3">◎</span></td><td><span class="g3">◎</span></td><td><span class="g0">×</span></td></tr>
<tr><td><strong>④ Argo Events</strong></td><td><span class="g2">○</span></td><td><span class="g2">○</span></td><td><span class="g2">○</span></td><td><span class="g2">○</span></td><td><span class="g1">△</span></td><td><span class="g0">×</span></td></tr>
<tr><td><strong>⑤ 自前 finalizer</strong></td><td><span class="g3">◎</span></td><td><span class="g1">△</span></td><td><span class="g3">◎</span></td><td><span class="g2">○</span></td><td><span class="g2">○</span></td><td><span class="g3">◎</span></td></tr>
<tr><td><strong>⑥ API stream</strong></td><td><span class="g2">○</span></td><td><span class="g1">△</span></td><td><span class="g1">△</span></td><td><span class="g1">△</span></td><td><span class="g1">△</span></td><td><span class="g0">×</span></td></tr>
</tbody>
</table>
</div>

<span class="g3">◎</span> そのまま満たす　<span class="g2">○</span> 満たすが条件付き　<span class="g1">△</span> 一部だけ、または大きな手当てが要る　<span class="g0">×</span> 満たせない。
「削除完了の検知」は、止まっていない状態でのタイミングの正しさ。止まっていた間の取りこぼしは「耐障害性」の列で評価した。
デプロイ完了の検知はどの方式でも取れるので列に立てていない（違いは重複の有無で、各方式の節に書いた）。

---

## 方式ごとの評価

### ① Argo CD Notifications

**削除完了: ×。** カタログの `on-deleted` は `when: app.metadata.deletionTimestamp != nil` で、説明文は "Application is deleted." だが、捉えるのは削除開始（[notifications_catalog/triggers/on-deleted.yaml](https://github.com/argoproj/argo-cd/blob/v3.5.3/notifications_catalog/triggers/on-deleted.yaml)）。
実測では削除要求の 0.06 秒後に届き、ペイロードの `finalizers` にはまだ `resources-finalizer.argocd.argoproj.io` を含む 3 つが残っていた。
条件を `deletionTimestamp != nil and app.status.health.status == 'Missing'` にしたカスタム trigger は、管理リソースが消えた直後（health が Missing になって 0.04 秒後）に発火した。これが Notifications で取れる最も遅い時点になる。
オブジェクトの消滅はどう書いても取れない。notifications-engine の controller は informer に `AddFunc` と `UpdateFunc` しか登録しておらず、キューから取り出したときにオブジェクトが無ければ何もせず戻る（[pkg/controller/controller.go](https://github.com/argoproj/notifications-engine/blob/0cff13b8a7178194dccd5c4edefa5a66b2cc08bc/pkg/controller/controller.go) の `NewController` と `processQueueItem` の `if !exists`）。

**デプロイ完了: 取れる。** カタログの `on-deployed` は operation が Succeeded かつ health が Healthy で、`oncePer: app.status.operationState?.syncResult?.revision`。
実測では operation が Succeeded になった時点（作成から 6.05 秒）で 1 回だけ届いた。送信済みの記録は annotation `notified.notifications.argoproj.io` に書かれる。

**認証認可: ◎。** 既存の `argocd-notifications-controller` の ServiceAccount のまま動き、追加の RBAC は要らない。送信先の資格情報は `argocd-notifications-secret` に置いて `$key` で参照する。
Application の annotation でアプリごとに購読を足せるので、アプリ側チームに送信先を選ばせることもできる。

**API 送信: ○。** webhook サービスは `method` / `path` / `body` を Go テンプレートで組める（`WebhookNotification`）。送信は go-retryablehttp で、既定は `retryMax: 3`・待ち 1〜5 秒（[pkg/services/webhook.go](https://github.com/argoproj/notifications-engine/blob/0cff13b8a7178194dccd5c4edefa5a66b2cc08bc/pkg/services/webhook.go)）。
それでも失敗すると送信済みの記録を戻すので、次の再評価で送り直される。再評価はアプリの更新か informer の再同期（60 秒、`notification_controller/controller/controller.go` の `resyncPeriod`）で起きる。
テンプレートで CloudEvents の structured 形式の本文を組めば、Knative Broker に直接入る。これは実測で確認した（`Content-Type: application/cloudevents+json` で POST し、Trigger の `type` フィルタを通って届いた）。

**マイクロサービス適正: △。** 送信先の追加は `argocd-notifications-cm` の編集で、Argo CD の設定に結びつく。ファンアウトは購読の数だけ個別に送る形になる。上のとおり Broker に 1 本出せば緩和できる。

**OTel 適正: △。** 出るのは Prometheus のメトリクス 2 本（`argocd_notifications_deliveries_total` と `argocd_notifications_trigger_eval_total`、ポート 9001、[monitoring.md](https://github.com/argoproj/argo-cd/blob/v3.5.3/docs/operator-manual/notifications/monitoring.md)）。
application-controller などには `--otlp-address` があるが、notifications controller のコマンドには見当たらない。実測で送信されたヘッダは `Content-Type` だけで、`traceparent` は付かない。

**耐障害性: △。** デプロイ通知は、コントローラが止まっていても復旧後の再評価で送られ、annotation の記録で重複も防がれる。
削除側は、実測（run4・run5）でコントローラが止まっている間に削除すると、復旧後も何も送られなかった。
Deployment の strategy は `Recreate` で 1 レプリカ構成（[manifests](https://github.com/argoproj/argo-cd/blob/v3.5.3/manifests/base/notification/argocd-notifications-controller-deployment.yaml)）。

### ② Kubernetes Job（PostSync / PostDelete hook）

**削除完了: △。** PostDelete hook は v2.10 から使える。ドキュメントは「全リソースが消えた後に実行し、hook が Healthy になるまで待ってから Application を消す」としている（[sync-waves.md の PostDelete Hooks](https://github.com/argoproj/argo-cd/blob/v3.5.3/docs/user-guide/sync-waves.md)）。
実測でも管理リソースが消えた 0.8 秒後に Job が送信し、その 2.5 秒後に Application が消えた。
つまり**管理リソースの消滅は保証するが、Application オブジェクトはまだある**。hook が失敗すると Application は `DeletionError` の状態で残るので、「hook が送った ＝ まもなく消える」とは言えても「消えた」ではない。

**デプロイ完了: 取れる。** PostSync hook は Healthy になった後に実行された（実測で Healthy の 1.3 秒後）。ただし hook が走るのは sync のたびで、Notifications の `oncePer` のような重複除けは無い。

**認証認可: △。** Job は各 Application のデプロイ先 namespace で、その namespace の ServiceAccount を使って動く。送信先の資格情報を**アプリの数だけ各 namespace に置く**ことになる。AppProject が Job の作成を許していることも前提になる。

**API 送信: ○。** コンテナの中身次第なので自由。再試行は `backoffLimit` とコンテナ内の実装で持つ。

**マイクロサービス適正: △。** hook は各アプリのマニフェストに入れる。送信先を足すには全アプリのマニフェストを変えることになる。

**OTel 適正: △。** Job の中で SDK を使えば出せるが、Argo CD 側から trace context は渡されない。

**耐障害性: ○。** 実行するのは application-controller なので、通知専用のコンポーネントが無い。実測（run5）で、ほかの監視系を全部止めていても PostDelete hook だけは送信した。
hook が失敗し続けると削除が止まるので、確実さと引き換えに削除が詰まる方向に倒れる。

### ③ Knative Eventing（ApiServerSource → Broker / Trigger）

**削除完了: ○。** `dev.knative.apiserver.resource.delete` はオブジェクトが消えた 5 ミリ秒後に届いた。本文は消える直前の Application そのもので、`deletionTimestamp` と最後に残った finalizer が入っている。
デプロイ完了は `resource.update` が更新のたびに届くだけなので（実測で 1 回の作成に 14 件）、Synced かつ Healthy かの判定は受け手が本文を見て行う。Trigger のフィルタは CloudEvents の属性で振り分けるもので、本文の `status` では絞れない。

**認証認可: ○。** ApiServerSource の ServiceAccount に applications の `get` / `list` / `watch` を、source の namespace に events の `create` / `patch` を与えた（実測で動いた最小の組）。送信先の資格情報は受け手の Knative Service の Secret に閉じる。

**API 送信: ○。** 外部への HTTP は受け手（Knative Service）の実装になる。Broker から受け手への配送は Trigger の `delivery`（retry・backoff・deadLetterSink）で設定できる。
受け手がレスポンス本文を返すと Broker が「CloudEvent ではない」として 500 扱いにし、ApiServerSource 側に失敗が返る。実測でこれを踏んだので、受け手は空の 2xx を返す。

**マイクロサービス適正: ◎。** 送信先の追加は Trigger 1 枚で、送る側を触らない。

**OTel 適正: ◎。** イベントは CloudEvents そのもの（実測で `Ce-Id` / `Ce-Type` / `Ce-Subject` などが付いた）。`config-observability` に `tracing-protocol` / `tracing-endpoint` / `metrics-protocol` があり、OTLP で出せる（[observability.yaml](https://github.com/knative/eventing/blob/knative-v1.23.0/config/core/configmaps/observability.yaml)）。
今回はトレースを有効にしていないので、`traceparent` が受け手まで届くかは確かめていない。

**耐障害性: ×。** adapter が止まっている間に消えた Application の delete は、復旧後も届かなかった（run5）。
adapter は informer の store を自前の delegate で実装していて、`Replace` と `Resync` が何もしない（[pkg/adapter/apiserver/delegate.go](https://github.com/knative/eventing/blob/knative-v1.23.0/pkg/adapter/apiserver/delegate.go)）。再接続時に一覧と突き合わせて「消えたもの」を出す仕組みが無いと読める。
配送路も、InMemoryChannel は README に "No Persistence" とある best effort なので、本番では Kafka などの永続チャネルにする。

### ④ Argo Events（resource EventSource → Sensor）

**削除完了: ○。** resource EventSource は informer に `DeleteFunc` を登録しており（[pkg/eventsources/sources/resource/start.go](https://github.com/argoproj/argo-events/blob/v1.9.11/pkg/eventsources/sources/resource/start.go)）、実測でオブジェクト消滅の 7 ミリ秒後に届いた。

**デプロイ完了: 重複する。** UPDATE を `status.health.status=Healthy` などのデータフィルタで絞ると、完了時に 4 回届いた。
さらに、削除開始の直後にも 2〜3 回届いた（run3 で 2 回、run6 で 3 回）。削除直後の更新でも status はまだ Synced / Healthy のままだからで、Lua スクリプトのフィルタで `deletionTimestamp` があるものを除けば止まった（完了時の 4 回は残る）。重複を除く仕組みは Sensor 側に無いので、受け手で冪等にする。

**認証認可: ○。** EventSource の ServiceAccount に applications の `get` / `list` / `watch`。送信先の資格情報は Sensor の trigger から Secret を参照する。

**API 送信: ○。** HTTP trigger は `payload` で本文の項目を写し、`retryStrategy` で再試行できる。

**マイクロサービス適正: ○。** EventBus を挟むので送る側と受ける側は分かれるが、送信先の追加は Sensor の編集になる。

**OTel 適正: △。** Prometheus のメトリクス（`argo_events_events_sent_total` など）はある。v1.9.11 の `pkg/` に OpenTelemetry への依存は見当たらず、HTTP trigger の送信に CloudEvents のヘッダは付かなかった（実測）。

**耐障害性: ×。** EventSource を止めている間に消えた Application の DELETE は届かなかった（run4・run5）。EventBus（JetStream）に入った後は永続化されるが、入る前に落ちたものは戻らない。
resource EventSource の HA は Active-Passive で、leader election は NATS か Kubernetes の Lease を使う（[docs/eventsources/ha.md](https://github.com/argoproj/argo-events/blob/v1.9.11/docs/eventsources/ha.md)）。

### ⑤ 自前の finalizer コントローラ

**削除完了: ◎。** Application に自分の finalizer を付けておき、`deletionTimestamp` があって**残りの finalizer が自分だけ**になったら送信し、送信が成功してから外す。
Argo CD はこれより前に `resources-finalizer` と `post-delete-finalizer` を外し終えているので、管理リソースの削除と PostDelete hook の完了が保証される。外した直後にオブジェクトが消える。
実測（run6）では送信から 45 ミリ秒後に Application が消えた。検証には Python の 40 行ほどの試作を使った。本番なら controller-runtime で書く。

**認証認可: △。** applications に `get` / `list` / `watch` に加えて `patch`（または `update`）が要る。Argo CD が持つ CR の `metadata.finalizers` に他者が書き込むことになるので、ほかの方式より権限が広い。

**API 送信: ◎。** 自分で書くので、ペイロード・再試行・冪等キー（Application の `uid` が使える）を自由に決められる。

**マイクロサービス適正: ○。** 単体では送信先がコードに入る。CloudEvent を Broker に出す形にすれば ◎ になる（推奨構成）。

**OTel 適正: ○。** 自分で OTel SDK を入れ、送信の span を切り、`traceparent` を付けて送れる。組み込みではないので ○ にした。

**耐障害性: ◎。** レベルトリガで、起動のたびに全件を見直すので、止まっていた間の削除も復旧後に拾う。実測（run4）では、コントローラを止めたまま削除すると Application は自分の finalizer 1 つを残して待ち、復旧後 2.4 秒で送信・消滅した。
送ってから外すので at-least-once で、外す前に落ちれば重複しうる。受け手は `uid` で冪等にする。

### ⑥ Argo CD API server の stream（`/api/v1/stream/applications`）

**削除完了: ○。** `DELETED` が消滅の 2 ミリ秒後に届いた。API server の broadcaster が informer の `OnDelete` を中継している（[server/broadcast/broadcaster.go](https://github.com/argoproj/argo-cd/blob/v3.5.3/server/broadcast/broadcaster.go)）。

**認証認可: △。** Kubernetes の RBAC ではなく Argo CD のアカウントとトークンで入る（実測は admin のセッショントークン）。常駐クライアントには `apiKey` を持つ専用アカウントと、`applications, get` を許す Argo CD の RBAC を用意し、長寿命トークンを Secret で持つ。

**API 送信・マイクロサービス適正・OTel 適正: △。** 受けたあとは全部自前クライアントの仕事で、⑤と同じく書く量はあるのに、⑤ほどの保証が得られない。

**耐障害性: ×。** broadcaster は、購読者のチャネルに空きが無いとイベントを捨てる（同ファイルの `// drop event if cannot send right away`）。切断中の削除も、再接続時の一覧に出てこないので取れない。

---

## 実測の条件と記録

kind v0.29.0（Kubernetes v1.33.1）の単一ノードに、次の最新リリースを入れて測った。

| 構成要素 | 版 | 備考 |
|---|---|---|
| Argo CD | v3.5.3 | 公式 `install.yaml`。Notifications の trigger / template は `argocd-notifications-cm` に自分で書いた |
| Knative Eventing | v1.23.0 | core・InMemoryChannel・MT channel broker。v1.23.0 は Kubernetes 1.34 以上を要求するので、`KUBERNETES_MIN_VERSION=1.33.0` で検査を外した。Knative Serving は入れず、Trigger の宛先は通常の Service |
| Argo Events | v1.9.11 | EventBus は JetStream |
| 自前 finalizer | 試作 | Python。1 秒ごとに全件を見直す |

テスト用の Application は、クラスタ内に置いた Helm リポジトリのチャート（ConfigMap・Deployment・PostSync Job・PostDelete Job）を `resources-finalizer.argocd.argoproj.io` 付き・自動 sync でデプロイするもの。
各方式の送信先は同じ受信用 Pod で、受け取った時刻とヘッダを記録した。

| run | 内容 | 結果 |
|---|---|---|
| run3 | 全方式を動かしたまま作成 → 削除 | ライフサイクルの図の時刻。Notifications の deployed は 1 回、Argo Events の deployed は 4 回、Knative の update は作成で 14 回 |
| run4 | 自前 finalizer を付けた状態で、通知系（Notifications・Knative・Argo Events・自前コントローラ）を全部止めて削除 → 25 秒後に復旧 | Application は自前 finalizer 1 つを残して待機。復旧後に自前コントローラが送信、Knative も（オブジェクトがまだあったので）delete を送った。Notifications と Argo Events は送らなかった |
| run5 | 自前 finalizer なしで、同じく全部止めて削除 → 消滅後に復旧 | 届いたのは PostDelete hook だけ。Notifications・Knative・Argo Events は 90 秒待っても何も送らなかった |
| run6 | Notifications にカスタム trigger（`deletionTimestamp` かつ Missing）を足して削除 | 管理リソース消滅の直後に発火。自前コントローラは消滅の 45 ミリ秒前に送信 |
| run7 | Notifications から CloudEvent を組んで Knative Broker に POST | Trigger の `type` フィルタを通って届いた。`Ce-Id` にはテンプレートで組んだ `uid-revision` が入る |

**確かめていないこと。** 複数レプリカでのフェイルオーバー時の挙動、Knative のトレースを有効にしたときの `traceparent` の伝搬、Kafka チャネルでの配送保証、Kyverno で作成時に finalizer を付ける構成、Robusta が CRD の削除を拾えるか。いずれも文献でも裏が取れていないので、上の評価には使っていない。
