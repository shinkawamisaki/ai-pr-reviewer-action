# AI PR Reviewer Action

A strict, rule-based AI Pull Request Reviewer GitHub Action using Google AI Studio (Gemini API).

This action automatically reviews Pull Requests against your project's custom rules (e.g., `.clinerules`, `CONTRIBUTING.md`). It detects security risks, hardcoded secrets, and architectural flaws, providing actionable feedback via GitHub's Suggested Changes format.

## Features
- **Strict Rule Enforcement**: Reviews code against your specific repository rules.
- **Security First**: Automatically masks sensitive information before sending it to the AI.
- **Ignore Patterns**: Skip unnecessary files (lock files, build artifacts) to save tokens and reduce noise.
- **Rate Limit Handling**: Built-in retry logic for Gemini API free tier users.
- **Developer Experience (DX)**: 
  - Suggests exact code modifications (````suggestion````).
  - Skips strict failure checks on Draft PRs.
  - Updates its own PR comments instead of spamming the timeline.
- **Persistence (Accumulation)**: Review results can be exported as a file and stored using GitHub Artifacts for future analysis and rule improvement.

## Usage

### 1. Get a Gemini API Key
Get a free API key from [Google AI Studio](https://aistudio.google.com/). Add it as a repository secret named `GEMINI_API_KEY`.

### 2. Set up GitHub Actions (In your target repository)
Create `.github/workflows/ai-pr-reviewer.yml` in your repository:

```yaml
name: AI PR Reviewer

on:
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review]

jobs:
  review:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Run AI PR Reviewer
        uses: shinkawamisaki/ai-pr-reviewer-action@v1
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          gemini_api_key: ${{ secrets.GEMINI_API_KEY }}
          # Optional: Path to your custom rules file. Defaults to '.clinerules'
          rules_file: '.clinerules'
          # Optional: Path to save the review result for accumulation
          output_path: 'review-result.md'
          # Optional: Comma-separated glob patterns to ignore
          exclude_patterns: '*-lock.json,*-lock.yaml,*.lock,dist/*,node_modules/*'

      - name: Upload review result
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: ai-review-report
          path: review-result.md
```

### 3. Rate Limits
If you are using the Gemini API free tier, large Pull Requests with many files may hit rate limits. This action includes basic retry logic, but for very large PRs, you may see some delays or partial reviews.

## Permissions
The action requires `pull-requests: write` permission to post and update comments.
