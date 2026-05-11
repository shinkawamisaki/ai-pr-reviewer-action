# AI PR Reviewer (by Misaki)

A strict, rule-based AI Pull Request Reviewer GitHub Action supporting multiple AI providers — Gemini, Claude, GPT-4o, and more.

This action automatically reviews Pull Requests against your project's custom rules (e.g., `.clinerules`, `CONTRIBUTING.md`). It detects security risks, hardcoded secrets, and architectural flaws, providing actionable feedback via GitHub's Suggested Changes format.

## Features
- **Multi-provider support**: Switch between Gemini, Claude, GPT-4o, and 100+ models supported by LiteLLM with a single `model` parameter.
- **Strict Rule Enforcement**: Reviews code against your specific repository rules.
- **Security First**: Automatically masks sensitive information before sending it to the AI.
- **Ignore Patterns**: Skip unnecessary files (lock files, build artifacts) to save tokens and reduce noise.
- **Rate Limit Handling**: Built-in retry logic for API free tier users.
- **Developer Experience (DX)**: 
  - Suggests exact code modifications (````suggestion````).
  - Skips strict failure checks on Draft PRs.
  - Updates its own PR comments instead of spamming the timeline.
- **Persistence (Accumulation)**: Review results can be exported as a file and stored using GitHub Artifacts for future analysis and rule improvement.
- **Multi-language Support**: Review comments can be generated in your preferred language (e.g., English, Japanese).

## Usage

### 1. Get an API Key and Register as a Secret

Get an API key from your preferred provider and register it in your repository's **Settings > Secrets and variables > Actions**.

| Provider | Where to get the key | Secret name |
|---|---|---|
| Google Gemini (default) | [Google AI Studio](https://aistudio.google.com/) | `GEMINI_API_KEY` |
| Anthropic Claude | [Anthropic Console](https://console.anthropic.com/) | `ANTHROPIC_API_KEY` |
| OpenAI | [OpenAI Platform](https://platform.openai.com/) | `OPENAI_API_KEY` |

### 2. Set up GitHub Actions (In your target repository)

Create `.github/workflows/ai-pr-reviewer.yml` in your repository:

#### Gemini (default, free tier available)

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
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Run AI PR Reviewer
        uses: shinkawamisaki/ai-pr-reviewer-action@v1
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          gemini_api_key: ${{ secrets.GEMINI_API_KEY }}
```

#### Switch to Claude

```yaml
      - name: Run AI PR Reviewer
        uses: shinkawamisaki/ai-pr-reviewer-action@v1
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}
          model: 'claude-opus-4-7'
```

#### Switch to GPT-4o

```yaml
      - name: Run AI PR Reviewer
        uses: shinkawamisaki/ai-pr-reviewer-action@v1
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          openai_api_key: ${{ secrets.OPENAI_API_KEY }}
          model: 'gpt-4o'
```

### 3. All Options

```yaml
      - name: Run AI PR Reviewer
        uses: shinkawamisaki/ai-pr-reviewer-action@v1
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          gemini_api_key: ${{ secrets.GEMINI_API_KEY }}
          # Optional: AI model to use (default: 'gemini/gemini-2.5-flash')
          model: 'gemini/gemini-2.5-flash'
          # Optional: Path to your custom rules file. Defaults to '.clinerules'
          rules_file: '.clinerules'
          # Optional: Path to save the review result for accumulation
          output_path: 'ai-review-report.md'
          # Optional: Comma-separated glob patterns to ignore (e.g., lock files, compiled output)
          exclude_patterns: '*-lock.json,*-lock.yaml,*.lock,dist/*,node_modules/*,vendor/*'
          # Optional: Output language for review comments (e.g., 'en-US' or 'ja-JP'). Defaults to 'ja-JP'.
          language: 'en-US'
```

### Supported Models (Examples)

| Model | `model` value | Required secret |
|---|---|---|
| Gemini 2.5 Flash (default) | `gemini/gemini-2.5-flash` | `GEMINI_API_KEY` |
| Gemini 2.5 Pro | `gemini/gemini-2.5-pro` | `GEMINI_API_KEY` |
| Claude Opus 4.7 | `claude-opus-4-7` | `ANTHROPIC_API_KEY` |
| Claude Sonnet 4.6 | `claude-sonnet-4-6` | `ANTHROPIC_API_KEY` |
| Claude Haiku 4.5 | `claude-haiku-4-5-20251001` | `ANTHROPIC_API_KEY` |
| GPT-4o | `gpt-4o` | `OPENAI_API_KEY` |
| GPT-4o mini | `gpt-4o-mini` | `OPENAI_API_KEY` |

For the full list of supported models, see [LiteLLM Providers](https://docs.litellm.ai/docs/providers).

### 4. Log Confirmation & Accumulation

If you set the `output_path`, you can download and review the AI's findings after the GitHub Action completes:

1. Open the **Actions** tab of the target repository.
2. Click on the latest workflow execution result.
3. Download the `ai-review-report` from the **Artifacts** section at the bottom of the page.

```yaml
      # Example: Storing the review result using GitHub Artifacts
      - name: Upload review report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: ai-review-report
          path: ai-review-report.md
```

### 5. Add Project Rules (Optional but Recommended)

Create a `.clinerules` or `REVIEW_GUIDELINES.md` file in the root of your repository to dictate how the AI should evaluate code.

Example `.clinerules`:
```markdown
# Project Guidelines
1. Never hardcode passwords or API keys. Always use environment variables.
2. Ensure proper error handling. Do not use bare `except:` or `catch(e)`.
3. All internal IP addresses must be configurable.
```

## Limitations

- **Prompt Injection**: Since PR diffs are passed directly to the AI prompt, malicious code comments could potentially manipulate the AI's judgment. AI review results should be treated as reference information, and final decisions should always be made by a human.
- **Masking Scope**: Masking is primarily targeted at literal strings in quotes. Secrets without quotes (e.g., certain JWTs) or non-standard variable names might not be detected.

## Permissions
The action requires `pull-requests: write` permission to post and update comments.

## Changelog

### [2.0.0] - 2026-05-12
- Multi-provider support via LiteLLM (Gemini, Claude, GPT-4o and 100+ models)
- Added `model` input parameter (default: `gemini/gemini-2.5-flash`)
- Added `anthropic_api_key` and `openai_api_key` input parameters

### [1.0.0] - 2026-05-10
- Initial release (Gemini 2.5-flash, multi-language, ignore patterns, file output)

## Author

**shinkawa.misaki**

- **GitHub**: [shinkawamisaki](https://github.com/shinkawamisaki)
- **YOUTRUST**: [shinkawa](https://youtrust.jp/users/shinkawa)
- **Email**: [shinkawa.misaki@gmail.com](mailto:shinkawa.misaki@gmail.com)

## License
Apache License 2.0
