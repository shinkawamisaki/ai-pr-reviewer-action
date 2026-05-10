# AI PR Reviewer Action

A strict, rule-based AI Pull Request Reviewer GitHub Action using Google AI Studio (Gemini API).

This action automatically reviews Pull Requests against your project's custom rules (e.g., `.clinerules`, `CONTRIBUTING.md`). It detects security risks, hardcoded secrets, and architectural flaws, providing actionable feedback via GitHub's Suggested Changes format.

## Features
- **Strict Rule Enforcement**: Reviews code against your specific repository rules.
- **Security First**: Automatically masks sensitive information before sending it to the AI.
- **Developer Experience (DX)**: 
  - Suggests exact code modifications (````suggestion````).
  - Skips strict failure checks on Draft PRs (allows testing without blocking).
  - Updates its own PR comments instead of spamming the timeline.
- **Cost Effective**: Uses `gemini-1.5-flash` via Google AI Studio API.

## Usage

### 1. Get a Gemini API Key
Get a free API key from [Google AI Studio](https://aistudio.google.com/). Add it as a repository secret named `GEMINI_API_KEY`.

### 2. Set up GitHub Actions
Create a file at `.github/workflows/ai-pr-reviewer.yml` in your repository:

```yaml
name: AI PR Reviewer

on:
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review]

jobs:
  review:
    runs-on: ubuntu-latest
    # Optional: Skip Draft PRs completely, or let it run to get feedback without blocking.
    # if: github.event.pull_request.draft == false
    
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
```

### 3. Add Project Rules (Optional but Recommended)
Create a `.clinerules` or `REVIEW_GUIDELINES.md` file in the root of your repository to dictate how the AI should evaluate code. 

Example `.clinerules`:
```markdown
# Project Rules
1. Never hardcode passwords or API keys. Always use environment variables.
2. Ensure proper error handling. Do not use bare `except:` or `catch(e)`.
3. All internal IP addresses must be configurable.
```

## Permissions
The action requires read/write permissions for pull requests. Ensure your `GITHUB_TOKEN` has the necessary scope (this is usually default, but check your Repository Settings > Actions > General > Workflow permissions).
