# Thin Harness, Fat Skills — どういう形式のハーネスがよいか（見立て）

> これは調べた事実ではなく**意見**。今後の AI エージェントによるコーディングを前提に、ハーネスの形式を選んだ見立てを書いた。事実として書いた部分（機能・引用）は、パターン・カタログと同じく公式ドキュメントか README で裏を取ってある。取れないものは「ユーザーの観察」と書き分けた。

{{figure}}

## 結論（意見）

**Thin Harness, Fat Skills。ループは自分で書かず薄く保ち、「検証」「境界」「知識」の 3 つに投資する。この 3 つを、持ち運べる形で置く。**
一言で言えば、エージェントを**どう動かすか**ではなく、エージェントの成果を**どう信じるか**に投資するハーネスである。

「Thin Harness, Fat Skills」は Garry Tan の言葉で、ユーザーが見つけた記事で知った。以下は、この見立てとの対応である。

| Garry Tan の主張（事実：原文の引用） | この見立てでの対応（意見） |
| --- | --- |
| ハーネスはモデルをループで回し、ファイルを読み書きし、文脈を管理し、安全を守るプログラム。そこは薄く保つ（"That's the “thin.”"） | ループは Claude Code や Codex CLI のものを借り、自分では書かない |
| 判断・手順・ドメイン知識は Markdown のスキルに書く。価値の 9 割はここにある（"This is where 90% of the value lives."） | **知識**に投資する。SKILL.md の形で書けば、エージェントを乗り換えても残る |
| 実行は決定的な道具に押し下げる。そこに信頼が宿る（"Deterministic is where trust lives."） | **検証**と**境界**に投資する。テスト・`make ci`・フック・サンドボックスは、どれも同じ入力に同じ結果を返す |

出典：

- 一次資料：Garry Tan「Thin Harness, Fat Skills」（2026-04、[garrytan/gbrain の docs/ethos/THIN_HARNESS_FAT_SKILLS.md](https://github.com/garrytan/gbrain/blob/master/docs/ethos/THIN_HARNESS_FAT_SKILLS.md)）。"I call it **thin harness, fat skills**." "Push intelligence UP into skills. Push execution DOWN into deterministic tooling. Keep the harness THIN."
- 紹介記事：[「Thin Harness, Fat Skills」とは？（Fyve、2026-04-13）](https://fyve.co.jp/claude-code/articles/thin-harness-fat-skills-guide)。「ハーネス（CLAUDE.md・settings.json等の設定層）は最小限に抑え、知識と手順はすべてSkillsに集約する」
- 言葉の主：記事は「元GoogleのSteve Yeggeが提唱した」と書く。しかし一次資料で Yegge が引かれているのは生産性の数字（"10x to 100x"）だけで、名付けたのは Tan 自身である（"I call it"）。このページは一次資料に従った
- 用語の違い：Tan の「ハーネス」はモデルを回すプログラムのことで、このカタログの 4 層で言えば主にループ層にあたる。記事の「ハーネス」は CLAUDE.md や settings.json などの設定層を指す。カタログの「ハーネス層」（ツール・権限・フック・索引）とは範囲が違う

| | 時間が経つと価値が減るもの | 価値が残る・増えるもの |
| --- | --- | --- |
| 何か | エージェントのループそのもの（モデル呼び出し、ツール実行、文脈管理） | **検証**：終わったと言える証拠を機械が確かめる仕組み（テスト、実アプリの操作、`make ci`） |
| | モデルの弱さを補うプロンプトの工夫（「必ず〜せよ」を並べる、言い回しで挙動を誘導する） | **境界**：サンドボックス、権限、worktree による隔離、取り消せない操作での停止 |
| | 特定ツールの落とし穴を書き留めたメモ | **知識**：自分のドメイン、組織の決めごと、過去の失敗 |
| | | **並列と統合**：複数のワーカーを走らせ、人のレビューを少なく保つ仕組み |
| なぜ | 各社が作り込んでいて追いつけない。モデルの版が上がると不要になるか、害になる。ツールの版が上がると古くなる | モデルが賢くなっても肩代わりできない。自律性が上がるほど重みが増す |

## 理由（意見）

第一に、ハーネスを取り巻く要素のうち、いちばん速く進むのはモデルである。ハーネスの中でモデルの代わりに考えている部分は、次の版で無駄になる。残るのは、モデルにはできない部分、つまり外界を確かめること、権限を与えること、固有の知識を渡すことだけである。

第二に、ボトルネックが「書く」から「信じる」に移った。Cursor の pstack（poteto-mode）の README は、速さではなく検証できるコードを売りにしている（"when you go deep on one agent and trust it to write good, verifiable code, you can truly parallelize with confidence"、[README](https://github.com/cursor/plugins/blob/main/pstack/README.md)）。pstack の評判が高いこと自体は**ユーザーの観察**で、裏は取っていない。

第三に、持ち運べる形式が複数のツールで共通になりつつある。スキル（`SKILL.md`）は Claude Code と Codex CLI の両方が同じ段階的読み込みで扱い、フックも両方にある（カタログの「スキルの段階的読み込み」「終了条件を満たすまで自動で続ける」の出典）。この形式で書いた資産はエージェントを乗り換えても残る。独自ループに書いた資産は、ループと一緒に古びる。

## 形式の比較

カタログの出典を 3 つの形式に分けた。「自分で書くもの」「試す手間」は各出典の README・公式ドキュメントから、評価は見立て。

| | 上に積むスキル集 | 実行基盤 | ホスト型製品 |
| --- | --- | --- | --- |
| 例 | [pstack / poteto-mode](https://github.com/cursor/plugins/tree/main/pstack) | [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness)、[Hermes Agent](https://github.com/NousResearch/hermes-agent) | [Devin](https://docs.devin.ai/get-started/devin-intro) |
| 自分で書くもの | 拡張点だけ（スキル、フック、MCP） | ループ全体 | なし |
| 試す手間 | プラグインを 1 つ入れるだけ（`/add-plugin pstack`）。エディタはいつものまま | 実行環境ごと乗り換える | 契約して作業を預ける（Web・Slack・API から渡し、PR で受け取る） |
| 中身を読めるか・持ち帰れるか | すべて Markdown。手順と原則を写せる | コードは読めるが、真似るには実装が要る | 読めない。受け取れるのは成果物だけ |
| 見立て | **勧める** | 学ぶ対象（読む）であって、乗る対象ではない | 検証と境界を自分で持てない |

カタログで未採用・部分的の {{gap_total}} 件を手間で分けると、手間 1（文面を足す）が {{effort_1}} 件、手間 2（フック・スクリプト・settings）が {{effort_2}} 件、手間 3（ハーネスの外の基盤か、Claude Code に無い機能が要る）が {{effort_3}} 件だった（`catalog.yaml` から生成時に数えている）。手間 3 の {{effort_3}} 件は {{effort_3_names}}。このうち独自ループでなければ実現できないのは「ツール呼び出しごとの LLM 審査」と「上限付きで、開始時に固定するメモリ」くらいで、残りは上に積む形のまま足せる。

## 自作ハーネス（core-principal）に当てはめると（意見）

| | 中身 |
| --- | --- |
| 方向 | **合っている**。Claude Code の上に積み、apm で配り、常駐ルールは橋渡しだけにしている |
| 足りない投資 | **検証**：上位 5 の 1 位「完了は検証の証拠で宣言し、証明したら止まる」。**境界**：サンドボックスと承認ポリシー。ハーネス層がいちばん薄い |
| 減らすもの | 版で変わる知識の散文（Orca の実測メモ `core-dispatch/references/orca.md` など）。検査（`make ci`、フック）に移すか、ツール公式のスキルに任せる |
| 続けるもの | ハーネス自体の計測（`make metrics`：ローカルのログからセッション・ツール呼び出し・フックの拒否を数える） |
