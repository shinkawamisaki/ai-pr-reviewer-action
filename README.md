# AI PR Reviewer Action

Google AI Studio (Gemini API) を活用した、ルールベースで厳格な AI Pull Request レビュアー GitHub Action です。

このアクションは、プロジェクト独自のルール（例: `.clinerules` や `CONTRIBUTING.md`）に基づいてPull Requestのコードを自動でレビューします。セキュリティリスク、ハードコードされたシークレット、アーキテクチャ上の欠陥などを検知し、GitHubの「Suggested Changes（修正案の提案）」形式で具体的な修正コードをフィードバックします。

## 主な機能 (Features)
- **厳格なルール適応**: あなたのリポジトリ独自のルールに従ってコードをレビューします。
- **セキュリティ・ファースト**: AIにデータを送る前に、ソースコード内の機密情報（パスワードやトークン、IPアドレスなど）を自動でマスク（秘匿化）します。
- **開発者体験 (DX) の向上**: 
  - そのまま取り込める具体的な修正コード（````suggestion````）を提案します。
  - Draft状態のPRでは、違反があってもActionを「FAIL（赤×）」にせず、開発の妨げになりません。
  - 毎回新しいコメントを投稿してタイムラインを荒らすのではなく、AIのコメントを上書き（Update）して綺麗に保ちます。
- **高コスパ**: Google AI Studio API の `gemini-1.5-flash` モデルを使用しており、高速かつ低コストで動作します。

## 使い方 (Usage)

### 1. Gemini APIキーの取得
[Google AI Studio](https://aistudio.google.com/) から無料のAPIキーを取得します。
取得したキーを、導入先リポジトリの **Settings > Secrets and variables > Actions** に `GEMINI_API_KEY` という名前で登録してください。

### 2. GitHub Actions の設定（利用する側のリポジトリでの作業）
このAI検閲官を「導入したいプロジェクト（あなたのアプリやインフラのリポジトリ）」に設定を追加します。

導入先リポジトリに `.github/workflows/` というフォルダ（なければ新規作成）を作り、その中に `ai-pr-reviewer.yml` という空のファイルを作成して、以下のコードをコピー＆ペーストしてください。これだけで「ワンパン」で導入可能です：

```yaml
name: AI PR Reviewer

on:
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review]

jobs:
  review:
    runs-on: ubuntu-latest
    # オプション: Draft状態のPRではワークフロー自体を動かしたくない場合はコメントアウトを外してください
    # if: github.event.pull_request.draft == false
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Run AI PR Reviewer
        uses: shinkawamisaki/ai-pr-reviewer-action@v1
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          gemini_api_key: ${{ secrets.GEMINI_API_KEY }}
          # オプション: 読み込ませたいルールファイルのパスを指定します（デフォルトは '.clinerules'）
          rules_file: '.clinerules'
```

### 3. プロジェクトルールの追加（推奨）
AIに「どういう基準でレビューしてほしいか」を教えるため、リポジトリの直下に `.clinerules` や `REVIEW_GUIDELINES.md` というファイルを作成します。

`.clinerules` の記述例:
```markdown
# プロジェクト憲法
1. パスワードやAPIキーは絶対にハードコーディングしないでください。必ず環境変数を使用してください。
2. 適切なエラーハンドリングを行ってください。単なる `except:` などの記述は禁止です。
3. 内部のIPアドレスは設定ファイルから読み込めるようにしてください。
```

## 必要な権限 (Permissions)
このアクションはPRに対してコメントを書き込む権限が必要です。通常はデフォルトで設定されていますが、うまく動かない場合は、リポジトリの **Settings > Actions > General > Workflow permissions** が「Read and write permissions」になっているか確認してください。


 [1.0.0] - 2026-05-10
- 初回リリース

## 作者 (Author)

**shinkawa.misaki**

- **GitHub**: [shinkawamisaki](https://github.com/shinkawamisaki)
- **YOUTRUST**: [shinkawa](https://youtrust.jp/users/shinkawa)
- **Email**: [shinkawa.misaki@gmail.com](mailto:shinkawa.misaki@gmail.com)

## ライセンス
Apache License 2.0