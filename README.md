# AI PR Reviewer (by Misaki)

Gemini、Claude、GPT-4o など複数のAIモデルに対応した、ルールベースで厳格な AI Pull Request レビュアー GitHub Action です。

このアクションは、プロジェクト独自のルール（例: `.clinerules` や `CONTRIBUTING.md`）に基づいてPull Requestのコードを自動でレビューします。セキュリティリスク、ハードコードされたシークレット、アーキテクチャ上の欠陥などを検知し、GitHubの「Suggested Changes（修正案の提案）」形式で具体的な修正コードをフィードバックします。

## 主な機能 (Features)
- **マルチプロバイダー対応**: Gemini / Claude / GPT-4o など、LiteLLM が対応する100以上のモデルを `model` パラメータ1つで切り替え可能。
- **厳格なルール適応**: あなたのリポジトリ独自のルールに従ってコードをレビューします。
- **Fail-Closed ゲート (v3)**: 合格は AI が「RESULT: PASS」を明示した場合のみ。プロンプトインジェクションの成功や形式逸脱で判定が得られない場合は「検閲不能」としてブロックします（`strict_verify` で制御）。
- **審査基準は base コミットから読む (v3)**: ルール・判例・プロンプトは PR 適用「前」のコミットから取得します。「ルールを骨抜きにするPR」をその骨抜き後のルールで審査してしまう自己参照の穴を塞ぎます。
- **プロンプトインジェクション対策 (v3)**: diff を `<diff>` デリミタで囲み、diff 内に埋め込まれた指示を実行しないようプロンプトで明示します。
- **判例ファイル対応 (v3)**: ルール（憲法）とは別に、過去の人間判断を記録した判例ファイル（`active_rules_file`）をルールより優先して適用できます。
- **プロンプトの外部ファイル化 (v3)**: レビュープロンプトをリポジトリ内のファイルに差し替え可能（`prompt_file`）。promptfoo 等の回帰テストと本番が同一プロンプトを読む構成にできます。
- **セキュリティ・ファースト**: AIにデータを送る前に、ソースコード内の機密情報（パスワードやトークン、IPアドレスなど）を自動でマスク（秘匿化）します。変数参照（`${VAR}` 等）は実値ではないためマスクせず、誤検知を防ぎます。
- **開発者体験 (DX) の向上**: 
  - そのまま取り込める具体的な修正コード（````suggestion````）を提案します。
  - Draft状態のPRでは、違反があってもマージをブロックせず開発の妨げになりません。Commit Status は Success ではなく **Pending** とし、Ready 転換後の再実行までゲートを閉じたまま保ちます（draft→ready のすり抜け防止）。
  - 毎回新しいコメントを投稿してタイムラインを荒らすのではなく、AIのコメントを上書き（Update）して綺麗に保ちます。
- **除外設定 (Ignore Patterns)**: `*.lock` や `dist/*` などの不要なファイルを除外して、APIコストの節約とノイズ削減が可能です。
- **レート制限への配慮**: API の無料枠利用時でも安定して動作するよう、簡易的なリトライロジックを内蔵しています。
- **ログの永続化（蓄積）**: レビュー結果を任意のパスにファイル出力できます。GitHub Actionsの Artifacts 機能と組み合わせることで、過去の全レビュー結果を「証跡」として溜めておくことが可能です。

## 使い方 (Usage)

### 1. APIキーの取得とシークレット登録

使いたいプロバイダーのAPIキーを取得し、導入先リポジトリの **Settings > Secrets and variables > Actions** に登録してください。

| プロバイダー | APIキー取得先 | シークレット名 |
|---|---|---|
| Google Gemini（デフォルト） | [Google AI Studio](https://aistudio.google.com/) | `GEMINI_API_KEY` |
| Anthropic Claude | [Anthropic Console](https://console.anthropic.com/) | `ANTHROPIC_API_KEY` |
| OpenAI | [OpenAI Platform](https://platform.openai.com/) | `OPENAI_API_KEY` |

### 2. GitHub Actions の設定（利用する側のリポジトリでの作業）

導入先リポジトリに `.github/workflows/ai-pr-reviewer.yml` を作成して、以下のコードをコピー＆ペーストしてください。

#### Gemini（デフォルト・無料枠あり）

```yaml
name: AI PR Reviewer (by Misaki)

on:
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review]

jobs:
  review:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
      statuses: write  # Commit Status（Draft=Pending ゲート）の投稿に必要
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Run AI PR Reviewer
        uses: shinkawamisaki/ai-pr-reviewer-action@v3
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          gemini_api_key: ${{ secrets.GEMINI_API_KEY }}
```

GitHub Variables でモデルを一元管理したい場合は、リポジトリ（または Organization）の **Settings > Secrets and variables > Actions > Variables** に `AI_REVIEWER_MODEL` を登録し、`model: ${{ vars.AI_REVIEWER_MODEL }}` と書くと、ワークフローを編集せずにモデルを切り替えられます。

#### Claude に切り替える場合

```yaml
      - name: Run AI PR Reviewer
        uses: shinkawamisaki/ai-pr-reviewer-action@v3
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}
          model: 'claude-opus-4-7'
```

#### GPT-4o に切り替える場合

```yaml
      - name: Run AI PR Reviewer
        uses: shinkawamisaki/ai-pr-reviewer-action@v3
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          openai_api_key: ${{ secrets.OPENAI_API_KEY }}
          model: 'gpt-4o'
```

### 3. 全オプション一覧

```yaml
      - name: Run AI PR Reviewer
        uses: shinkawamisaki/ai-pr-reviewer-action@v3
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          gemini_api_key: ${{ secrets.GEMINI_API_KEY }}
          # オプション: 使用するモデル（デフォルト: 'gemini/gemini-2.5-flash'）
          model: 'gemini/gemini-2.5-flash'
          # オプション: 読み込ませたいルールファイルのパス（デフォルト: '.clinerules'）
          # ※ v3 から PR の base コミットから読み込みます（自己参照の遮断）。
          #    PR で新規追加した基準ファイルは採用されず、次の PR から有効になります
          rules_file: '.clinerules'
          # オプション: 判例ファイル（過去の人間判断）。ルールより優先して適用されます
          active_rules_file: 'logs/active_rules.md'
          # オプション: レビュープロンプトをリポジトリ内のテンプレートに差し替え
          # （プレースホルダ: {{rules}} / {{active_rules}} / {{diff}} / {{language}}）
          prompt_file: 'prompts/reviewer_prompt.txt'
          # オプション: fail-closed 制御（デフォルト: 'true'）。
          # 'false' にすると判定不能時（インジェクション・API障害等）にブロックせず通します
          strict_verify: 'true'
          # オプション: Commit Status の投稿（デフォルト: 'true'）。statuses: write 権限が必要
          set_commit_status: 'true'
          # オプション: Commit Status のコンテキスト名（デフォルト: 'AI PR Reviewer'）
          status_context: 'AI PR Reviewer'
          # オプション: レビュー結果をファイルとして保存したい場合にパスを指定
          output_path: 'ai-review-report.md'
          # オプション: レビュー対象から除外するファイルのパターン
          exclude_patterns: '*-lock.json,*-lock.yaml,*.lock,dist/*,node_modules/*,vendor/*'
          # オプション: 出力言語（'ja-JP' または 'en-US'）
          language: 'ja-JP'
```

### 強制ゲートとして使う（必須ステータスチェック・推奨）

Draft→Ready のすり抜け防止（Pending ゲート）は **Commit Status** が担います。ワークフローのジョブ結果ではなく、このアクションが投稿する Status コンテキスト（デフォルト: `AI PR Reviewer`）を必須チェックに指定してください。

1. リポジトリの **Settings > Branches > Branch protection rules** で対象ブランチのルールを開く
2. **Require status checks to pass before merging** を有効化
3. ステータス一覧から `AI PR Reviewer` を選択（一度実行されると候補に現れます）

これにより「Draft 中は警告のみ・Ready になったら再実行で PASS するまでマージ不可」が機械的に強制されます。

### 対応モデル一覧（例）

| モデル | `model` に指定する値 | 必要なシークレット |
|---|---|---|
| Gemini 2.5 Flash（デフォルト） | `gemini/gemini-2.5-flash` | `GEMINI_API_KEY` |
| Gemini 2.5 Pro | `gemini/gemini-2.5-pro` | `GEMINI_API_KEY` |
| Claude Opus 4.7 | `claude-opus-4-7` | `ANTHROPIC_API_KEY` |
| Claude Sonnet 4.6 | `claude-sonnet-4-6` | `ANTHROPIC_API_KEY` |
| Claude Haiku 4.5 | `claude-haiku-4-5-20251001` | `ANTHROPIC_API_KEY` |
| GPT-4o | `gpt-4o` | `OPENAI_API_KEY` |
| GPT-4o mini | `gpt-4o-mini` | `OPENAI_API_KEY` |

その他 LiteLLM が対応するモデルは [LiteLLM Providers](https://docs.litellm.ai/docs/providers) を参照してください。

### 4. ログの確認・蓄積方法

`output_path` を設定した場合、GitHub Actions の実行完了後に、以下の手順で AI の指摘内容をダウンロードして確認できます。

1. 対象リポジトリの **Actions** タブを開く。
2. 最新のワークフロー実行結果をクリック。
3. 画面最下部の **Artifacts** セクションにある `ai-review-report` をクリックしてダウンロード。

```yaml
      # レビュー結果を GitHub Artifact として保存する例
      - name: Upload review report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: ai-review-report
          path: ai-review-report.md
```

### 5. プロジェクトルールの追加（推奨）

AIに「どういう基準でレビューしてほしいか」を教えるため、リポジトリの直下に `.clinerules` や `REVIEW_GUIDELINES.md` というファイルを作成します。

`.clinerules` の記述例:
```markdown
# プロジェクト憲法
1. パスワードやAPIキーは絶対にハードコーディングしないでください。必ず環境変数を使用してください。
2. 適切なエラーハンドリングを行ってください。単なる `except:` などの記述は禁止です。
3. 内部のIPアドレスは設定ファイルから読み込めるようにしてください。
```

## 制限事項 (Limitations)

- **プロンプトインジェクション**: v3 で多層対策（`<diff>` デリミタ＋指示の明示＋Fail-Closed 判定）を導入しましたが、LLM の性質上、操作の可能性をゼロにはできません。AIレビューの結果は参考情報として扱い、最終的な判断は必ず人間が行ってください。
- **機密情報マスキングの範囲**: マスキング処理はキーワード（password / secret / token 等）に続くリテラル値を対象としています。JWTやBearerトークンなど、非標準の変数名を持つシークレットは検出されない場合があります。

## 必要な権限 (Permissions)
- `pull-requests: write` — PRへのコメント投稿（必須）
- `statuses: write` — Commit Status の投稿（v3 推奨。無い場合は警告を出してコメントのみで動作し、Draft=Pending ゲートは機能しません）

うまく動かない場合は、リポジトリの **Settings > Actions > General > Workflow permissions** が「Read and write permissions」になっているか確認してください。


## 変更履歴 (Changelog)

### [3.0.0] - 2026-06-12
セキュリティゲートとしての構造強化（Fail-Closed 化）。

- **[Breaking] Fail-Closed 判定**: 合格は「RESULT: PASS」の明示一致のみ。判定不能な出力（インジェクション成功・形式逸脱）は `strict_verify: 'true'`（デフォルト）でブロックされます。従来の「FAILを含まなければ合格」は廃止
- **[Breaking] 審査基準を PR の base コミットから読むよう変更**（`rules_file` / `active_rules_file` / `prompt_file`）。ルールを骨抜きにするPRを骨抜き前のルールで審査します
- `<diff>` デリミタと指示0によるプロンプトインジェクション対策
- レビュープロンプトを外部テンプレートファイル化（`prompt_file` で差し替え可能。本番と回帰テストで同一プロンプトを共有する構成が可能に）
- 判例ファイル対応（`active_rules_file`。ルールより優先適用）
- Commit Status 投稿（`set_commit_status` / `status_context`）。Draft PR の FAIL は Success ではなく **Pending** とし、draft→ready 転換のすり抜けを防止
- マスク処理の誤検知修正: 変数参照（`${VAR}` / `process.env.X` 等）をマスクしないよう改善

### [2.0.0] - 2026-05-12
- マルチプロバイダー対応（LiteLLM 経由で Gemini / Claude / GPT-4o ほか100以上のモデルをサポート）
- `model` 入力パラメータを追加（デフォルト: `gemini/gemini-2.5-flash`）
- `anthropic_api_key`、`openai_api_key` 入力パラメータを追加

### [1.0.0] - 2026-05-10
- 初回リリース（Gemini 2.5-flash 対応、マルチ言語、除外設定、ファイル出力機能搭載）

## 作者 (Author)

**shinkawa.misaki**

- **GitHub**: [shinkawamisaki](https://github.com/shinkawamisaki)
- **YOUTRUST**: [shinkawa](https://youtrust.jp/users/shinkawa)
- **Email**: [shinkawa.misaki@gmail.com](mailto:shinkawa.misaki@gmail.com)

## ライセンス
Apache License 2.0
