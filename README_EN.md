# AI PR Reviewer (by Misaki)

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
- **Highly Cost-Effective**: Powered by Google AI Studio's `gemini-2.5-flash` model for high-speed and low-cost operations.
- **Persistence (Accumulation)**: Review results can be exported as a file and stored using GitHub Artifacts for future analysis and rule improvement.
- **Multi-language Support**: Review comments can be generated in your preferred language (e.g., English, Japanese).

## Usage

### 1. Get a Gemini API Key
Get a free API key from [Google AI Studio](https://aistudio.google.com/). Add it as a repository secret named `GEMINI_API_KEY`.

### 2. Set up GitHub Actions (In your target repository)
Create `.github/workflows/ai-pr-reviewer.yml` in your repository:

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
          # Optional: Path to your custom rules file. Defaults to '.clinerules'
          rules_file: '.clinerules'
          # Optional: Path to save the review result for accumulation
          output_path: 'ai-review-report.md'
          # Optional: Comma-separated glob patterns to ignore (e.g., lock files, compiled output)
          exclude_patterns: '*-lock.json,*-lock.yaml,*.lock,dist/*,node_modules/*,vendor/*'
          # Optional: Output language for review comments (e.g., 'en-US' or 'ja-JP'). Defaults to 'ja-JP'.
          language: 'en-US'

      # Example: Storing the review result using GitHub Artifacts
      - name: Upload review report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: ai-review-report
          path: ai-review-report.md
```

### 3. Log Confirmation & Accumulation
If you set the `output_path`, you can download and review the AI's findings after the GitHub Action completes by following these steps:

1. Open the **Actions** tab of the target repository.
2. Click on the latest workflow execution result.
3. Download the `ai-review-report` from the **Artifacts** section at the bottom of the page.

Reviewing these logs regularly helps in analyzing AI feedback and identifying areas for rule improvement.

### 4. Add Project Rules (Optional but Recommended)
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

## Author
**shinkawa.misaki**

- **GitHub**: [shinkawamisaki](https://github.com/shinkawamisaki)
- **YOUTRUST**: [shinkawa](https://youtrust.jp/users/shinkawa)
- **Email**: [shinkawa.misaki@gmail.com](mailto:shinkawa.misaki@gmail.com)

## License
Apache License 2.0
