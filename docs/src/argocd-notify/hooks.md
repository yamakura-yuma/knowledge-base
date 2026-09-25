# ② PostSync / PostDelete Job

> application-controller が、アプリのマニフェストに入っている hook（Job）を、sync の後や削除の途中で作って実行する。Job の中から送信先へ HTTP で送る。**PostDelete が捉えるのは、管理リソースは消えたが Application はまだ残っている時点。**

<p class="eli5">引っ越し業者は、荷物を全部運び出すと「終わりました」と電話をくれますが、それは部屋の鍵を返す前です。Argo CD の PostDelete hook も同じ形で、アプリの Pod や ConfigMap を消し終えたあと、アプリ自身の Job（一回だけ動いて終わる Pod）が知らせを送ります。ところがその時点で、アプリの登録（Application）はまだ残っています。しかも Job が失敗すると Argo CD は片づけを終えないので、宛先が落ちていると削除そのものが止まります。</p>

<figure class="dd">
<svg viewBox="0 32 960 232" role="img" aria-labelledby="dd-hooks-title dd-hooks-desc">
<title id="dd-hooks-title">PostDelete hook が送る時点と、Application が消える時点</title>
<desc id="dd-hooks-desc">削除を依頼してから 3.45 秒で管理リソースが消え、4.29 秒に hook の Job が通知を送り、Application が消えるのは 6.80 秒（run3 の実測）。</desc>
<defs><marker id="dd-hooks-ar" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon class="dd-ah" points="0 0, 8 3, 0 6"/></marker><marker id="dd-hooks-ara" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon class="dd-ah-acc" points="0 0, 8 3, 0 6"/></marker><marker id="dd-hooks-arr" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon class="dd-ah-red" points="0 0, 8 3, 0 6"/></marker></defs>
<rect class="dd-paper" x="0" y="32" width="960" height="232"/>
<line class="dd-base" x1="60" y1="164" x2="920" y2="164" marker-end="url(#dd-hooks-ar)"/>
<line class="dd-tick" x1="60" y1="160" x2="60" y2="168"/>
<line class="dd-tick" x1="180" y1="160" x2="180" y2="168"/>
<line class="dd-tick" x1="300" y1="160" x2="300" y2="168"/>
<line class="dd-tick" x1="420" y1="160" x2="420" y2="168"/>
<line class="dd-tick" x1="540" y1="160" x2="540" y2="168"/>
<line class="dd-tick" x1="660" y1="160" x2="660" y2="168"/>
<line class="dd-tick" x1="780" y1="160" x2="780" y2="168"/>
<line class="dd-tick" x1="900" y1="160" x2="900" y2="168"/>
<path class="dd-line dd-acc" d="M574.8,100 L574.8,92 Q574.8,92 574.8,92 L876.0,92 Q876.0,92 876.0,92 L876.0,100"/>
<line class="dd-drop" x1="60" y1="164" x2="60" y2="128"/>
<line class="dd-drop" x1="474.0" y1="164" x2="474.0" y2="200"/>
<line class="dd-drop" x1="876.0" y1="164" x2="876.0" y2="200"/>
<line class="dd-drop" x1="574.8" y1="164" x2="574.8" y2="100"/>
<rect class="dd-store" x="60" y="48" width="816.0" height="28" rx="4"/>
<text class="dd-name" x="76" y="67" text-anchor="start">Application はまだある</text>
<text class="dd-lbl" x="60" y="244" text-anchor="middle">0 秒</text>
<text class="dd-lbl" x="180" y="244" text-anchor="middle">1</text>
<text class="dd-lbl" x="300" y="244" text-anchor="middle">2</text>
<text class="dd-lbl" x="420" y="244" text-anchor="middle">3</text>
<text class="dd-lbl" x="540" y="244" text-anchor="middle">4</text>
<text class="dd-lbl" x="660" y="244" text-anchor="middle">5</text>
<text class="dd-lbl" x="780" y="244" text-anchor="middle">6</text>
<text class="dd-lbl" x="900" y="244" text-anchor="middle">7</text>
<rect class="dd-mask" x="670.4" y="78" width="110" height="16" rx="2"/>
<text class="dd-lbl dd-acc-t" x="725.4" y="90" text-anchor="middle">あと 2.5 秒</text>
<circle class="dd-dot" cx="60" cy="164" r="4"/>
<circle class="dd-dot" cx="474.0" cy="164" r="4"/>
<circle class="dd-dot" cx="876.0" cy="164" r="4"/>
<circle class="dd-dot-acc" cx="574.8" cy="164" r="6"/>
<text class="dd-sub" x="68" y="124" text-anchor="start">削除を依頼</text>
<text class="dd-sub" x="466.0" y="216" text-anchor="end">Pod・ConfigMap が消える（3.45 秒）</text>
<text class="dd-name dd-acc-t" x="586.8" y="128" text-anchor="start">hook の Job が通知（4.29 秒）</text>
<text class="dd-sub" x="868.0" y="216" text-anchor="end">Application が消える（6.80 秒）</text>
</svg>
</figure>





## アーキテクチャ

```diagram
title: PostSync / PostDelete のアーキテクチャ
caption: hook はアプリのデプロイ先 namespace で、アプリの一部として動く
height: 400
zones:
  - {label: "argocd namespace", kind: platform, box: [10, 30, 330, 330]}
  - {label: "デプロイ先 namespace（demo）", kind: app, box: [360, 30, 330, 330]}
  - {label: "外部", kind: ext, box: [710, 30, 280, 330]}
nodes:
  - {id: app, kind: app, label: "Application（CR）", mono: ["finalizers:", "resources-finalizer…", "post-delete-finalizer…"], box: [25, 60, 300, 86]}
  - {id: ctl, label: "application-controller", lines: ["hook を作る・待つ・消す"], mono: ["StatefulSet（シャード）"], box: [25, 200, 300, 70]}
  - {id: res, label: "管理リソース", mono: ["Deployment / ConfigMap …"], box: [375, 60, 300, 54]}
  - {id: ps, label: "Job: notify-postsync", mono: ["hook: PostSync"], box: [375, 150, 300, 54]}
  - {id: pd, label: "Job: notify-postdelete", mono: ["hook: PostDelete"], box: [375, 240, 300, 54]}
  - {id: sec, kind: state, label: "Secret（送信先の資格情報）", mono: ["アプリごとに置く"], box: [375, 305, 300, 44]}
  - {id: ext, kind: ext, label: "任意の HTTP", mono: ["Job の中で curl など"], box: [725, 150, 250, 54]}
edges:
  - {from: ctl, to: app, kind: patch, label: "finalizer を外す"}
  - {from: ctl, to: res, kind: http, via: [[350, 87]], label: apply/delete, dy: -4}
  - {from: ctl, to: ps, kind: http}
  - {from: ctl, to: pd, kind: http}
  - {from: ps, to: ext, kind: http, label: HTTP}
  - {from: pd, to: ext, kind: http}
```

- **状態を持つ場所は Application の finalizer。** PostDelete hook があると、Argo CD は `post-delete-finalizer.argocd.argoproj.io` と `…/cleanup` を自動で付ける（`controller/appcontroller.go` の `SetPostDeleteFinalizer`）。hook が Healthy になるまで、この finalizer は外れない
- PostDelete は v2.10 から使える（[sync-waves.md](https://github.com/argoproj/argo-cd/blob/v3.5.3/docs/user-guide/sync-waves.md)）

## 権限分離

```diagram
title: PostSync / PostDelete の権限分離
caption: Platform は AppProject で Job の作成を許すだけ。送信と資格情報は App 側に閉じる
height: 330
zones:
  - {label: "Platform 側", kind: platform, box: [10, 30, 480, 260]}
  - {label: "App 側（デプロイ先 namespace）", kind: app, box: [510, 30, 480, 260]}
nodes:
  - {id: ctl, label: "application-controller", mono: ["デプロイ先に Job を作る権限（Argo CD 既定）"], box: [25, 60, 450, 54]}
  - {id: proj, kind: crd, label: "AppProject", mono: ["namespaceResourceWhitelist に batch/Job"], box: [25, 150, 450, 54]}
  - {id: man, kind: crd, label: "アプリのマニフェスト（Git）", mono: ["hook の Job を App チームが書く"], box: [525, 60, 450, 54]}
  - {id: job, label: "Job の Pod", mono: ["namespace の ServiceAccount で動く"], box: [525, 150, 450, 54]}
  - {id: sec, kind: state, label: "Secret", mono: ["送信先の資格情報（アプリの数だけ置く）"], box: [525, 225, 450, 50]}
edges:
  - {from: proj, to: man, kind: rbac, label: "Job を許可"}
  - {from: ctl, to: job, kind: http}
```

- **Platform の役割は小さい。** AppProject が Job の作成を許していれば済む（AppProject の `namespaceResourceWhitelist` / `Blacklist`、[projects.md](https://github.com/argoproj/argo-cd/blob/v3.5.3/docs/user-guide/projects.md)）
- **越境:** Job はデプロイ先 namespace で、その namespace の ServiceAccount を使って動く。他チームの Application を見る経路は無い。ただし通知の本文は Job が自分で組むので、Job を書けるチームなら、他のアプリ名を名乗る通知を送れてしまう。受け手が送り元を検証する必要がある
- **資格情報:** 送信先の資格情報は、アプリの数だけ各 namespace に置く

## 導入・運用の労力

### 基盤側の作業

| 作業 | 頻度 |
|---|---|
| AppProject で Job の作成を許す | 初回だけ |
| 削除が PostDelete hook で詰まったときの手当て（hook を消す） | 障害のたび |

### 利用者側の作業

| 作業 |
|---|
| 全アプリのマニフェストに hook の Job を書く |
| 送信先の資格情報を各 namespace に置いて更新する |
| 受け手を用意する |

## 評価

**削除完了の検知: △。** ドキュメントは「全リソースが消えた後に実行し、hook が Healthy になるまで待ってから Application を消す」としている。実測では、管理リソースが消えた 0.8 秒後に Job が送信し、その 2.5 秒後に Application が消えた（[run3](report.html#run3)）。hook が失敗すると、Application は `DeletionError` の状態で残る。つまり「送った」とは言えても、「消えた」とは言えない。

**デプロイ完了: 取れる。** PostSync は Healthy になった後に実行された（Healthy の 1.3 秒後）。ただし sync のたびに実行され、重複を除く仕組みは無い。

**検知層の耐障害性: ◎。** 実行するのは application-controller 自身なので、通知専用の部品が無い。ほかの通知系を全部止めた [run5](report.html#run5) でも、PostDelete hook だけは送った。

**配送層の回復性: △。** 再試行は Job の `backoffLimit` と、コンテナ内の実装（今回は `curl --retry 5`）に頼る。DLQ は無い。

**配送保証: △。** Job が成功するまで Argo CD が待つので、削除時は at-least-once になる。PostSync は sync のたびに走るため、重複する。

**可用性: ×。** hook が失敗し続けると、Application の削除がそこで詰まる。送信先が落ちていると、削除ができなくなる。

**疎結合: ×。** hook は各アプリのマニフェストに入る。送信先を変えるには、全アプリのマニフェストを変えることになる。

**スケーラビリティ: ×。** ファンアウトは Job の中に自分で書く。

**可観測性: △。** Job の中で OTel SDK を使えば出せる。Argo CD から trace context は渡されない。

**セキュリティ・権限分離: △。** 分離はできるが、資格情報がアプリごとに散らばる。通知の偽装も防げない。

**運用負荷: △。** 部品は増えないが、全アプリに Job を書くことになる。

**レイテンシ: △。** 管理リソースの消滅から 0.8 秒で送信。Application の消滅は、その 2.5 秒後。
