# ② PostSync / PostDelete Job

> application-controller が、アプリのマニフェストに入っている hook（Job）を、sync の後や削除の途中で作って実行する。Job の中から送信先へ HTTP で送る。**PostDelete が捉えるのは、管理リソースは消えたが Application はまだ残っている時点。**

<div class="grwb">
<svg class="wb" viewBox="0 0 1000 620" role="img" aria-label="グラレコ：PostDelete hook が送るのは、管理リソースが消えたあと・Application が消える前。宛先が落ちると削除が詰まる">
<path class="hl" d="M40,52 L620,48"/>
<text class="th" x="40" y="58">送ったとき、まだ消えていない</text>
<text class="ts" x="660" y="56">PostDelete hook の順番（run3）</text>

<g filter="url(#wob)">
  <!-- 時間軸 0s=100, 3.45s=486, 4.29s=580, 6.80s=860 -->
  <path class="wk" d="M90,440 L950,440" marker-end="url(#ak)"/>
  <path class="wk thin" d="M100,430 L100,452 M486,430 L486,452 M580,430 L580,452 M860,430 L860,452"/>
  <!-- 行1: 管理リソース -->
  <rect class="wk fw" x="110" y="104" width="60" height="44" rx="4"/>
  <rect class="wk fw" x="184" y="104" width="60" height="44" rx="4"/>
  <path class="wk thin" d="M250,126 L470,126" />
  <path class="wk" d="M466,106 L506,146 M506,106 L466,146"/>
  <!-- 行2: Job が走って送る -->
  <circle class="wb-b fw" cx="560" cy="196" r="12"/>
  <path class="wb-b" d="M560,208 L556,238 M558,218 L538,230 M558,218 L580,212 M556,238 L540,260 M556,238 L574,258"/>
  <path class="wb-b thin" d="M520,214 L532,214 M516,226 L530,226"/>
  <path class="wb-b" d="M584,200 l30,0 l0,20 l-30,0 z M584,200 l15,11 l15,-11"/>
  <path class="wb-b" d="M618,208 C680,190 720,176 780,178" marker-end="url(#ab)"/>
  <path class="wk fw" d="M790,156 h110 a10,10 0 0 1 10,10 v32 a10,10 0 0 1 -10,10 h-86 l-16,14 l4,-14 h-12 a10,10 0 0 1 -10,-10 v-32 a10,10 0 0 1 10,-10 z"/>
  <!-- 行3: Application はまだある -->
  <rect class="wb-b fb" x="100" y="318" width="760" height="46" rx="10"/>
  <path class="hl" d="M586,392 L852,392"/>
  <path class="wk" d="M580,386 q0,14 14,14 L706,400 q14,0 14,14 q0,-14 14,-14 L846,400 q14,0 14,-14"/>
  <path class="wk" d="M868,300 q18,-14 34,0 q18,-8 26,10 q16,6 4,22 q6,18 -16,18 q-12,14 -30,2 q-20,6 -22,-14 q-14,-14 4,-38 z"/>
  <!-- 失敗したら -->
  <path class="wr dash" d="M560,266 C560,470 500,500 470,520" marker-end="url(#ar)"/>
  <circle class="wr fw" cx="430" cy="545" r="22"/>
  <path class="wr" d="M416,531 L444,559 M444,531 L416,559"/>
  <rect class="wr fr" x="140" y="520" width="200" height="50" rx="8"/>
  <rect class="wk fw" x="100" y="530" width="30" height="24" rx="4"/>
  <path class="wk" d="M106,530 v-8 a9,9 0 0 1 18,0 v8"/>
  <path class="wr" d="M404,545 L352,545" marker-end="url(#ar)"/>
</g>

<text class="ts" x="96" y="476">0 秒</text>
<text class="ts" x="468" y="476">3.5 秒</text>
<text class="ts" x="564" y="476">4.3 秒</text>
<text class="ts" x="840" y="476">6.8 秒</text>
<text class="ts" x="40" y="96">管理リソース</text>
<text x="518" y="100">消えた</text>
<text class="ts tb" x="440" y="192">hook の Job</text>
<text x="820" y="190">通知</text>
<text class="ts" x="40" y="310">Application</text>
<text class="tb" x="140" y="348">まだある</text>
<text class="ts" x="640" y="428">あと 2.5 秒</text>
<text x="868" y="376">消滅</text>
<text class="ts tr" x="468" y="600">宛先が落ちると</text>
<text class="tr" x="152" y="552">削除が詰まる</text>
<text class="ts" x="150" y="600">DeletionError のまま残る</text>
</svg>
</div>





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
