# AI PR Reviewer (by Misaki)

A strict, rule-based AI Pull Request Reviewer GitHub Action supporting multiple AI providers — Gemini, Claude, GPT-4o, and more.

This action automatically reviews Pull Requests against your project's custom rules (e.g., `.clinerules`, `CONTRIBUTING.md`). It detects security risks, hardcoded secrets, and architectural flaws, providing actionable feedback via GitHub's Suggested Changes format.

## Features
- **Multi-provider support**: Switch between Gemini, Claude, GPT-4o, and 100+ models supported by LiteLLM with a single `model` parameter.
- **Strict Rule Enforcement**: Reviews code against your specific repository rules.
- **Fail-Closed Gate (v3)**: A pass requires an explicit "RESULT: PASS" from the AI. Output with no parseable verdict (successful prompt injection, format drift) is treated as "unverifiable" and blocks the merge (controlled by `strict_verify`).
- **Review criteria read from the base commit (v3)**: Rules, precedents, and the prompt template are fetched from the commit *before* the PR is applied, closing the self-reference hole where a PR that waters down the rules would be judged by its own watered-down rules.
- **Prompt-injection countermeasures (v3)**: The diff is wrapped in `<diff>` delimiters and the prompt explicitly forbids following instructions embedded in it.
- **Precedents file (v3)**: Past human review decisions (`active_rules_file`) can be applied with priority over the general rules.
- **External prompt template (v3)**: Replace the review prompt with a file in your repository (`prompt_file`), so a regression-test harness (e.g. promptfoo) and production share the exact same prompt.
- **Security First**: Automatically masks sensitive information before sending it to the AI. Variable references (`${VAR}` etc.) are not masked, avoiding false positives.
- **Ignore Patterns**: Skip unnecessary files (lock files, build artifacts) to save tokens and reduce noise.
- **Rate Limit Handling**: Built-in retry logic for API free tier users.
- **Developer Experience (DX)**: 
  - Suggests exact code modifications (````suggestion````).
  - Draft PRs never block the merge, but the commit status is set to **Pending** (not Success), so flipping draft → ready cannot smuggle a failing PR past a required status check.
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
      statuses: write  # Required to post the commit status (draft=pending gate)
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Run AI PR Reviewer
        uses: shinkawamisaki/ai-pr-reviewer-action@v3
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          gemini_api_key: ${{ secrets.GEMINI_API_KEY }}
```

To manage the model centrally via GitHub Variables, register `AI_REVIEWER_MODEL` under **Settings > Secrets and variables > Actions > Variables** and write `model: ${{ vars.AI_REVIEWER_MODEL }}` — you can then switch models without editing the workflow.

#### Switch to Claude

```yaml
      - name: Run AI PR Reviewer
        uses: shinkawamisaki/ai-pr-reviewer-action@v3
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}
          model: 'claude-opus-4-7'
```

#### Switch to GPT-4o

```yaml
      - name: Run AI PR Reviewer
        uses: shinkawamisaki/ai-pr-reviewer-action@v3
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          openai_api_key: ${{ secrets.OPENAI_API_KEY }}
          model: 'gpt-4o'
```

### 3. All Options

```yaml
      - name: Run AI PR Reviewer
        uses: shinkawamisaki/ai-pr-reviewer-action@v3
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          gemini_api_key: ${{ secrets.GEMINI_API_KEY }}
          # Optional: AI model to use (default: 'gemini/gemini-2.5-flash')
          model: 'gemini/gemini-2.5-flash'
          # Optional: Path to your custom rules file. Defaults to '.clinerules'
          # Note: since v3, read from the PR *base* commit (self-reference cut).
          # Criteria files newly added by a PR are not adopted until the next PR
          rules_file: '.clinerules'
          # Optional: Precedents file (past human decisions). Takes priority over the rules
          active_rules_file: 'logs/active_rules.md'
          # Optional: Replace the review prompt with a template in your repository
          # (placeholders: {{rules}} / {{active_rules}} / {{diff}} / {{language}})
          prompt_file: 'prompts/reviewer_prompt.txt'
          # Optional: Fail-closed control (default: 'true').
          # Set 'false' to pass when no verdict can be produced (injection, API outage)
          strict_verify: 'true'
          # Optional: Post a commit status (default: 'true'). Requires statuses: write
          set_commit_status: 'true'
          # Optional: Context name of the commit status (default: 'AI PR Reviewer')
          status_context: 'AI PR Reviewer'
          # Optional: Path to save the review result for accumulation
          output_path: 'ai-review-report.md'
          # Optional: Comma-separated glob patterns to ignore (e.g., lock files, compiled output)
          exclude_patterns: '*-lock.json,*-lock.yaml,*.lock,dist/*,node_modules/*,vendor/*'
          # Optional: Output language for review comments (e.g., 'en-US' or 'ja-JP'). Defaults to 'ja-JP'.
          language: 'en-US'
```

### Using it as an enforced gate (required status check, recommended)

The draft → ready protection (pending gate) is carried by the **commit status**, not the workflow job result. Mark the status context posted by this action (default: `AI PR Reviewer`) as a required status check:

1. Open **Settings > Branches > Branch protection rules** for the target branch
2. Enable **Require status checks to pass before merging**
3. Select `AI PR Reviewer` from the list (it appears after the first run)

This mechanically enforces "warning-only while draft; once ready, no merge until a re-run passes".

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

- **Prompt Injection**: v3 introduces layered countermeasures (`<diff>` delimiters, explicit instructions, fail-closed verdict parsing), but with LLMs the risk cannot be reduced to zero. Treat AI review results as reference information; final decisions should always be made by a human.
- **Masking Scope**: Masking targets literal values following keywords (password / secret / token, etc.). Secrets with non-standard variable names might not be detected.

## Permissions
- `pull-requests: write` — post and update PR comments (required)
- `statuses: write` — post the commit status (recommended for v3; without it the action warns and works comment-only, and the draft=pending gate is not enforced)

## Changelog

### [3.0.0] - 2026-06-12
Structural hardening as a security gate (fail-closed).

- **[Breaking] Fail-closed verdict**: a pass requires an explicit "RESULT: PASS". Unparseable output (successful injection, format drift) blocks the merge under `strict_verify: 'true'` (default). The old "no FAIL found == pass" logic is removed
- **[Breaking] Review criteria are read from the PR base commit** (`rules_file` / `active_rules_file` / `prompt_file`), so a PR that waters down the rules is judged by the pre-change rules
- Prompt-injection countermeasures: `<diff>` delimiters + instruction 0
- External prompt template (`prompt_file`; production and regression tests can share the exact same prompt)
- Precedents file support (`active_rules_file`, applied with priority over the rules)
- Commit status posting (`set_commit_status` / `status_context`). A failing draft PR gets **Pending** instead of Success, closing the draft → ready bypass
- Masking false-positive fix: variable references (`${VAR}` / `process.env.X` etc.) are no longer masked

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
