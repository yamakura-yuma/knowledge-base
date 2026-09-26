# ⑤ finalizer 方式（Metacontroller / 自作）

> **位置づけ:** Namespace を基盤の Job が消す前提では、推奨構成（概要ページ）に置き換わる。この方式は、削除完了を Application の消滅で定義する場合の代替として残す。
>
> Application に自分の finalizer を付けておき、**残っている finalizer が自分だけ**になった時点で送信する。送信に成功してから finalizer を外す。6 方式の中で、削除完了を保証したうえで送れるのはこの方式だけ。finalizer の付け外しは Metacontroller の DecoratorController に任せ、自分で書くのは状態を持たない Webhook 1 つにとどめる。controller-runtime での自作は、得るものが少ない。

<p class="eli5">Kubernetes のオブジェクトには「まだ捨てないで」という札（finalizer）を付けられます。札が一枚でも残っていれば、削除を頼んでもオブジェクトは消えずに待ちます。この方法では、アプリの登録（Application）に自分の札を付けておき、Argo CD の札が外れて自分の札だけになったら知らせを送り、送れたら自分の札を外します。だから止まっていても取りこぼしません。その代わり、札を外す係が止まると、全チームの削除が待たされます。</p>

<!-- archify: finalizer.architecture -->

**図の読み方**

- ① Application に札（finalizer）が 4 枚付いている。すべて基盤側
- ② application-controller が Argo CD の札を外していく
- ③ Metacontroller が自分の札を付け外しする。⚠ applications への書き込み権限が要り、止まると全チームの削除が待つ（評価マトリクス「可用性 ×」「セキュリティ △」）
- ④ 残りが自分の札だけになったら finalize hook が送る
- ⑤ 利用者側は受け手だけ

（色と線の読み方: 橙の破線の枠が基盤側、赤の破線の枠が利用者側。緑の線は主な流れ、赤の線と「⚠」は問題点、紫の破線は鍵などの参照。）




## アーキテクチャ

```diagram
title: finalizer 方式のアーキテクチャ
caption: 状態は Application の finalizer 自身が持つ。Metacontroller が付け外しと再試行を受け持ち、hook は状態を持たない
height: 400
zones:
  - {label: "argocd namespace", kind: platform, box: [10, 30, 330, 330]}
  - {label: "metacontroller / notify namespace", kind: platform, box: [360, 30, 330, 330]}
  - {label: "送信先", kind: ext, box: [710, 30, 280, 330]}
nodes:
  - {id: app, kind: app, label: "Application（CR）", box: [25, 60, 300, 44]}
  - {id: fin, kind: state, label: "metadata.finalizers", mono: ["resources-finalizer.argocd…", "post-delete-finalizer.argocd…", "metacontroller.io/decorator…"], box: [25, 130, 300, 86]}
  - {id: argo, label: "application-controller", mono: ["argocd の finalizer を順に外す"], box: [25, 250, 300, 54]}
  - {id: mc, label: "Metacontroller", lines: ["DecoratorController"], mono: ["付け外し・resync・再試行"], box: [375, 60, 300, 70]}
  - {id: dc, kind: crd, label: "DecoratorController（CR）", mono: ["resources: applications", "hooks: sync / finalize"], box: [375, 160, 300, 66]}
  - {id: hook, label: "finalize hook（Webhook）", mono: ["状態なし・約 30 行・2 レプリカ"], box: [375, 255, 300, 54]}
  - {id: ext, kind: ext, label: "送信先 / Broker", mono: ["CloudEvent（Ce-Id = uid）"], box: [725, 255, 250, 54]}
edges:
  - {from: mc, to: app, kind: watch, label: watch}
  - {from: mc, to: fin, kind: patch, via: [[350, 170]], label: "付ける / 外す", dy: -4}
  - {from: argo, to: fin, kind: patch}
  - {from: mc, to: dc, kind: watch}
  - {from: mc, to: hook, kind: http, via: [[690, 95], [690, 240], [525, 240]], label: "finalize 要求"}
  - {from: hook, to: ext, kind: ce, label: "送信"}
```

**流れ:**

1. DecoratorController に `finalize` hook を定義すると、Metacontroller は対象の Application に finalizer `metacontroller.io/decoratorcontroller-<名前>` を付ける（[decoratorcontroller.md の Finalize Hook](https://github.com/metacontroller/metacontroller/blob/master/docs/src/api/decoratorcontroller.md)、`pkg/controller/decorator/controller.go`）。
2. Application が削除されると、Metacontroller は `finalizing: true` を付けて hook を呼ぶ。
3. hook は、自分以外の finalizer が残っているうちは `finalized: false` を返す。残りが自分だけになったら送信し、成功した場合に限って `finalized: true` を返す。
4. `finalized: true` を受け取ると、Metacontroller が finalizer を外し、Application が消える。

**hook の中身** は、試作で約 30 行だった。受け取った JSON の `object.metadata.finalizers` を見て、送るかどうかを決めるだけ。状態は持たない。

## 導入・運用の労力

**この部品は Application に書き込むので、基盤側の持ち物になる。** 利用者側に置いてはいけない。

**試作の行数は、本番の量ではない。** 実測した試作の規模は次のとおり。

| 試作 | 行数 | 持っていないもの |
|---|---:|---|
| Metacontroller の finalize hook（Python） | 29 | テスト、コンテナイメージ、CI |
| そのマニフェスト（DecoratorController・Deployment・Service） | 31 | — |
| 自作 controller の試作（Python、1 秒ごとに全件を list） | 32 | watch、リーダー選出、送信失敗時のバックオフ、メトリクス、テスト、コンテナイメージ、CI |
| そのマニフェスト（SA・Role・RoleBinding・Deployment） | 33 | — |

### 基盤側の作業

| 作業 | Metacontroller ＋ hook | 自作（controller-runtime） |
|---|---|---|
| 本体の導入 | Metacontroller 本体。CRD は 3 種で、CompositeController と DecoratorController はクラスタスコープ、ControllerRevision は namespace スコープ。StatefulSet 1 つ | 自分のコントローラの Deployment。CRD は無い |
| 権限を絞る | 既定の ClusterRole は `*/*/*`。applications の get/list/watch/patch/update、metacontroller.k8s.io の自分の CR、namespaces の get/list/watch、events、leases まで絞った。絞った ClusterRole は 29 行・5 ルールで、動作を確認した（[run11](report.html#run11)）。namespaces を外すと list が Forbidden になり、試行錯誤が要った | 必要な分だけを最初から書く（applications の get/list/watch/update/patch、leases、events） |
| HA | `--leader-election` を付けて 2 レプリカ。リーダーを殺しても、15 秒の Lease のあとにもう一方が引き継ぎ、削除中の Application も完了して通知も 1 通届いた（[run11](report.html#run11)） | Manager の `LeaderElection: true` で 2 レプリカ |
| アップグレードへの追従 | Metacontroller は過去 1 年で 21 リリース、マイナーは 6 つ | controller-runtime は過去 1 年で 12 リリース、マイナーは 4 つ。追従のたびに再ビルドと再テストが要る |
| hook の運用 | hook の Deployment と Service（2 レプリカ）。コンテナイメージとその CI | コントローラ自体のイメージと CI |
| finalizer が残って削除が止まったとき（runbook） | ① 削除中のまま一定時間残っている Application を検知する（`deletionTimestamp` があり、残りの finalizer が自分だけのもの）② hook と送信先の状態を確かめる ③ 送信を諦める判断をしたら、`kubectl patch app <name> --type json -p '[{"op":"remove","path":"/metadata/finalizers/<i>"}]'` で自分の finalizer を外し、通知を送らなかったことを記録する | 同じ |
| アンインストール | 先に全 Application から自分の finalizer を外す。外さずに本体を消すと、以後の削除がすべて止まる | 同じ |
| 作成時の finalizer | 止まっている間に作られて消えた Application を取りこぼさないよう、Kyverno の mutate などで作成時に付ける（任意、実測していない） | 同じ |

### 利用者側の作業

受け手を用意すること（CloudEvent を受け、`id` で重複を消す）だけ。Application にも Argo CD の設定にも触らない。Broker を挟む場合は、自分の namespace に Trigger を置く。

### 自作の規模の見積もり（見積もり）

controller-runtime で本番に出す場合の規模を見積もった。**実装して数えた値ではなく、見積もり。**

| 部分 | 見積もり（行） |
|---|---:|
| Reconciler（finalizer の付け外し、送信、エラーで再キュー） | 120〜180 |
| main（Manager、leader election、メトリクス、ヘルスチェック） | 60〜90 |
| CloudEvent の送信（属性、traceparent、タイムアウト） | 40〜60 |
| テスト（envtest で、付ける・外す・失敗・競合） | 200〜350 |
| マニフェスト（RBAC・Deployment・PDB・ServiceMonitor） | 100〜150 |
| Dockerfile と CI | 40〜80 |
| 合計 | 約 560〜900 |

### 結論（労力を数えたうえで）

前の版の「自作にする理由は薄い」は、基盤側の負荷を数えずに出した結論だった。数えると、次のように分かれる。

- **Metacontroller:** 自分で書くコードは少ない（hook 29 行）。その代わり、汎用の強い ClusterRole を持つ部品を 1 つ抱える。絞る作業と、21 リリース/年への追従が要る。
- **自作:** 権限は最小にできる。その代わり、見積もりで 560〜900 行のコードと、テスト・イメージ・CI の保守を抱える。

**どちらが軽いかは、基盤チームがすでに何を運用しているかで決まる。** Go のコントローラを CI 込みで運用している組織なら、自作の限界費用は小さい。そうでなければ Metacontroller のほうが軽い。一方、**検知の確実さと配送保証は、どちらでも同じ。**

## 実装仕様（自作する場合）

| 項目 | 仕様 |
|---|---|
| Reconciler の分岐 | ① 削除中でなければ、自分の finalizer を付ける ② 削除中で、残りの finalizer が自分だけなら、Broker ingress に CloudEvent を POST する ③ 2xx なら、楽観ロック（resourceVersion 付きの update）で finalizer を外す ④ 失敗したら error を返し、workqueue の指数バックオフに任せる ⑤ それ以外（Argo CD の finalizer が残っている）は何もしない |
| 作成直後の競合 | 作成直後に削除されると、finalizer を付ける前に消えうる。防ぐなら Kyverno の mutate で作成時に付ける |
| RBAC | applications の get/list/watch/update/patch、coordination.k8s.io の leases、events の create/patch |
| HA | leader election を有効にして 2 レプリカ |
| CloudEvent | `id = <uid>:deleted`、`type = com.example.argocd.app.deleted`、`source = argocd/applications`、`subject = <name>`、拡張属性に `project`。`traceparent` を付ける |
| 宛先障害の切り離し | Broker が永続化した土台なら、202 を受けた時点で finalizer を外してよい。宛先の障害は Broker 側の retry と DLQ が受け持つので、削除は止まらない（[run16](report.html#run16) で、アプリ側の宛先を常に 500 にしても、削除は完了した） |
| 運用 | 削除中のまま残った Application のアラート、finalizer を手で外す手順、アンインストール前の一括除去（上の表） |

### PingSource による突き合わせとの比較

| 観点 | finalizer（自作 / Metacontroller） | PingSource による突き合わせ |
|---|---|---|
| 権限 | applications への書き込み（patch/update） | get/list だけ（Namespace なら namespaces の get/list/watch） |
| 削除を止めるか | 止める（止まると全チームの削除が止まる） | 止めない |
| 停止中の削除 | 拾う（Application が待つ） | 拾う（uid 一覧と比べる） |
| 遅延 | ms 単位 | 最大で周期 1 回分（最短 1 分） |
| 1 周期のうちの作成と削除 | 拾う（作成時に finalizer が付いていれば） | ADD を記録しないと取りこぼす |
| 状態 | Application の finalizer | uid 一覧（ConfigMap か受け手の DB） |
| 実測 | [run4](report.html#run4)・[run10](report.html#run10)・[run11](report.html#run11) | [run12](report.html#run12)・[run13](report.html#run13)・[run15](report.html#run15) |

## 権限分離

```diagram
title: finalizer 方式の権限分離
caption: Application に書き込むので、基盤側が持つ部品になる。利用者は送信先で受けるだけ
height: 330
zones:
  - {label: "基盤側", kind: platform, box: [10, 30, 480, 260]}
  - {label: "利用者側", kind: app, box: [510, 30, 480, 260]}
nodes:
  - {id: mc, label: "Metacontroller（基盤が運用）", mono: ["ClusterRole は既定で */*/*。絞ること"], box: [25, 60, 450, 54]}
  - {id: dc, kind: crd, label: "DecoratorController と hook", mono: ["クラスタスコープの CR"], box: [25, 140, 450, 54]}
  - {id: adm, kind: crd, label: "admission（任意）", mono: ["作成時に finalizer を足す（Kyverno など）"], box: [25, 220, 450, 54]}
  - {id: sub, label: "受け手", mono: ["uid で冪等に受ける"], box: [525, 60, 450, 54]}
  - {id: sec, label: "受け手の Secret", mono: ["送信先の資格情報は利用者が持つ"], box: [525, 140, 450, 54]}
edges:
  - {from: dc, to: mc, kind: rbac}
  - {from: mc, to: sub, kind: ce, label: "hook から送信"}
```

- **越境:** 利用者側は Application に触れない。DecoratorController はクラスタスコープの CR なので、作れるのは基盤側だけになる。
- **資格情報:** 直接送る場合、送信先の資格情報は hook が持つ（基盤側）。Broker を挟めば、送信先ごとの受け手（利用者側）に閉じる。

## 評価

**削除完了の検知: ◎。** 自分の finalizer だけが残った時点で、Argo CD はすでに `resources-finalizer` と `post-delete-finalizer` を外し終えている。管理リソースの削除と PostDelete hook の完了が保証された状態で送れる。実測では、自前の試作は消滅の 45 ms 前に送信した（[run6](report.html#run6)）。Metacontroller の hook では、送信からオブジェクトの消滅まで約 10 ms だった（[run10](report.html#run10)）。

**検知層の耐障害性: ◎。** Metacontroller と hook を止めたまま削除すると、Application は Metacontroller の finalizer を 1 つだけ残して待った（[run10](report.html#run10)）。25 秒後に復旧させると、hook が送信し、約 16 秒後に Application が消えた。自前の試作でも同じ動きだった（[run4](report.html#run4)）。

**配送層の回復性: ○。** 送信先を常に 500 にすると、hook は `finalized: false` を返し続けた。Metacontroller は hook を呼び直し、実測では 4 秒後、30 秒後（`resyncPeriodSeconds: 30`）と再送した（[run10](report.html#run10)）。送信先を戻すと、次の呼び出しで送れて Application が消えた。DLQ は無い。送れるまで、削除も完了しない。

**配送保証: ◎。** 送ってから `finalized: true` を返すので、at-least-once になる。応答の前に落ちると重複する。CloudEvent の `Ce-Id` に Application の `uid` を入れ、受け手で重複を除く。

**可用性: ×。** Metacontroller が止まっている間は、削除が完了しない。`--leader-election` を付けて複数レプリカで動かす（[configuration.md](https://github.com/metacontroller/metacontroller/blob/master/docs/src/guide/configuration.md)）。既定のマニフェストは 1 レプリカ。複数レプリカでの動きは実測していない。

**疎結合: ○。** 直接送る形だと、送信先が hook の中に入る。Broker を挟めば、送信先の追加は Trigger 側で済む。

**スケーラビリティ: △。** Metacontroller はリーダー 1 つで処理する。hook は水平に増やせる。

**可観測性: ○。** Metacontroller は `--metrics-address` で Prometheus のメトリクスを出す。送信の span と `traceparent` は hook の側で付ける。

**セキュリティ・権限分離: △。** 既定の ClusterRole が広い。絞るのは基盤側の仕事になる。

**運用負荷: ○。** 増える部品は Metacontroller と hook。自作のコントローラを保守するよりは軽い。

**レイテンシ: ○。** 最後の Argo CD の finalizer が外れると、Metacontroller の watch がそれを拾って hook を呼ぶ。[run10](report.html#run10) では、送信から消滅まで約 10 ms だった。
