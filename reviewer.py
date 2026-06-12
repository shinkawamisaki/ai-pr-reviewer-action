#!/usr/bin/env python3
"""
AI PR Reviewer Action
A strict, rule-based AI Pull Request Reviewer supporting multiple AI providers via LiteLLM.

v3 hardening — the gate is designed to fail closed:
- A verdict requires an explicit "RESULT: PASS" line. Output matching neither PASS nor
  FAIL (successful prompt injection, format drift) is treated as "unverifiable" and
  handled by the strict_verify contract instead of silently passing.
- Review criteria (rules file, precedents file, prompt template) are read from the PR
  *base* commit via the GitHub Contents API, so a PR that waters down the rules is still
  judged by the pre-change rules (self-reference cut).
- The diff is wrapped in <diff> delimiters and the prompt forbids following instructions
  embedded in it.
- The prompt lives in an external template file, so a regression-test harness (e.g.
  promptfoo) can exercise the exact same prompt the action uses in production.
- Draft PRs with violations get a *pending* commit status instead of a green check:
  GitHub does not re-trigger "synchronize" on ready_for_review, so a green check on a
  failing draft could be smuggled past a required status check by flipping it to ready.
"""

import os
import sys
import re
import json
import time
import fnmatch
import requests
import litellm

HTTP_TIMEOUT = 30
# Backoff before retrying the AI call: absorbs transient 429/503 without hammering the API.
RETRY_BACKOFF_SECONDS = (5, 15)
MAX_AI_ATTEMPTS = 3
# Default prompt template bundled with the action (same directory as this script).
BUNDLED_PROMPT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts", "reviewer_prompt.txt")

# ==============================================================================
# GitHub API Helpers
# ==============================================================================
def make_json_headers(token):
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }

def make_diff_headers(token):
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3.diff",
        "X-GitHub-Api-Version": "2022-11-28"
    }

def make_raw_headers(token):
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.raw",
        "X-GitHub-Api-Version": "2022-11-28"
    }

def get_pr_diff(repository, pr_number, headers):
    url = f"https://api.github.com/repos/{repository}/pulls/{pr_number}"
    resp = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    return resp.text

def get_base_file_content(repository, path, base_sha, raw_headers, workspace):
    """Fetch a review-criteria file from the PR *base* commit (self-reference cut).

    Reading criteria from the checked-out PR head would let a PR that waters down the
    rules be judged by its own watered-down rules. Reading from the base commit judges
    "this change under the pre-change rules"; the diff itself is still taken from the
    PR, so the change is fully reviewed.

    The fetch does not depend on PR contents (an attacker cannot force it to fail), so
    *transient* API errors fall back to the workspace (head) copy with a warning. A 404
    is different: it means the file does not exist in the base commit, and a PR author
    can produce that state at will by newly adding the file. Falling back to the head
    copy there would inject brand-new, PR-controlled criteria into the trusted sections
    of the prompt (outside the <diff> delimiters) — exactly the self-reference hole this
    function exists to close. So a 404 returns 'absent' and callers fall to their safe
    defaults; newly added criteria files take effect from the *next* PR.

    Returns (content, source) where source is 'base' | 'workspace' | 'absent' | 'empty'.
    """
    url = f"https://api.github.com/repos/{repository}/contents/{path}?ref={base_sha}"
    try:
        resp = requests.get(url, headers=raw_headers, timeout=HTTP_TIMEOUT)
        if resp.status_code == 200:
            return resp.text, "base"
        if resp.status_code == 404:
            print(f"::notice::'{path}' does not exist in the base commit (newly added in this PR?). "
                  "Not using the head copy (self-reference cut); it takes effect from the next PR.")
            return "", "absent"
        print(f"::warning::Failed to fetch '{path}' from the base commit (HTTP {resp.status_code}). Falling back to the head copy.")
    except Exception:
        print(f"::warning::Error fetching '{path}' from the base commit. Falling back to the head copy.")

    # Confine the fallback to the workspace. The *_file inputs are repository paths
    # by contract, but os.path.join passes absolute paths ("/etc/passwd") and "../"
    # traversal through untouched. Whatever is read here is embedded into the prompt
    # and sent to the AI provider, so a misconfigured or malicious path must not be
    # able to exfiltrate files outside the checkout. realpath also resolves symlinks
    # before the containment check.
    workspace_root = os.path.realpath(workspace)
    workspace_path = os.path.realpath(os.path.join(workspace_root, path))
    if workspace_path != workspace_root and not workspace_path.startswith(workspace_root + os.sep):
        print(f"::warning::'{path}' resolves outside the workspace. Refusing to read it.")
        return "", "empty"
    if os.path.exists(workspace_path):
        with open(workspace_path, "r", encoding="utf-8") as f:
            return f.read(), "workspace"
    return "", "empty"

def post_or_update_comment(repository, pr_number, headers, body_text):
    url = f"https://api.github.com/repos/{repository}/issues/{pr_number}/comments"
    resp = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    comments = resp.json()

    bot_comment_id = None
    for c in comments:
        if "🤖 AI PR Reviewer" in c.get("body", ""):
            bot_comment_id = c["id"]
            break

    if bot_comment_id:
        update_url = f"https://api.github.com/repos/{repository}/issues/comments/{bot_comment_id}"
        resp = requests.patch(update_url, headers=headers, json={"body": body_text}, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
    else:
        resp = requests.post(url, headers=headers, json={"body": body_text}, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()

def set_commit_status(repository, sha, headers, state, description, context, enabled):
    """Post a commit status that can be used as a required status check.

    The commit status (not the workflow job result) is what carries the draft-PR
    "pending" semantics, so repositories wanting the full gate should mark this status
    context as a required check. Posting requires `statuses: write`; if the token lacks
    it we warn instead of failing, so comment-only setups keep working.
    """
    if not enabled or not sha:
        return
    url = f"https://api.github.com/repos/{repository}/statuses/{sha}"
    data = {
        "state": state,
        "description": description[:140],
        "context": context,
    }
    try:
        resp = requests.post(url, headers=headers, json=data, timeout=HTTP_TIMEOUT)
        if resp.status_code >= 400:
            print(f"::warning::Failed to set commit status (HTTP {resp.status_code}). "
                  "Grant 'statuses: write' permission, or disable with set_commit_status: 'false'.")
    except Exception:
        print("::warning::Failed to set commit status (network error).")

# ==============================================================================
# Security Masking (Redaction)
# ==============================================================================
def redact_sensitive_info(text):
    """Mask sensitive information before sending to the AI API.

    Variable *references* (${VAR} / $VAR / {var} / process.env.X / os.environ[...]) are
    not secret values, so they are excluded via negative lookahead. Masking references
    rewrites the diff itself and makes the reviewer flag legitimate code as broken
    (e.g. `token ${GITHUB_TOKEN}` mangled into `token: [REDACTED]}` caused a false
    FAIL). Literal secrets never start with $ or {, so the protection is not weakened.
    """
    if not text:
        return text
    text = re.sub(r'(?i)(password|secret|token|api[_-]?key|credentials)["\'\s:=]+(?!\$|\{|process\.env|os\.environ)[^\s"\'},]+', r'\1: [REDACTED]', text)
    text = re.sub(r'\b(?:10\.|172\.(?:1[6-9]|2[0-9]|3[0-1])\.|192\.168\.)[0-9.]+\b', '[REDACTED_IP]', text)
    return text

# ==============================================================================
# AI call with retry
# ==============================================================================
def call_ai_with_retry(ai_model, prompt):
    """Call the AI API, absorbing transient errors (429/503/empty response).

    Returns the response text, or raises after all attempts fail. No cross-vendor
    fallback on purpose: the reviewer model is an intentional choice (writer/reviewer
    independence), and silently switching vendors would also require credentials the
    workflow was never granted.
    """
    last_error = "unknown error"
    for attempt in range(MAX_AI_ATTEMPTS):
        try:
            response = litellm.completion(
                model=ai_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
            )
            result_text = (response.choices[0].message.content or "").strip()
            if not result_text:
                raise ValueError("empty response")
            return result_text
        except Exception as e:
            last_error = str(e)
            retryable = any(token in last_error for token in ("429", "503", "empty response", "overloaded"))
            if retryable and attempt < MAX_AI_ATTEMPTS - 1:
                delay = RETRY_BACKOFF_SECONDS[min(attempt, len(RETRY_BACKOFF_SECONDS) - 1)]
                print(f"::warning::AI API call failed with a transient error. Retrying in {delay}s... (Attempt {attempt + 1}/{MAX_AI_ATTEMPTS})")
                time.sleep(delay)
                continue
            break
    raise RuntimeError(f"AI API call failed after retries: {last_error}")

# ==============================================================================
# Main Logic
# ==============================================================================
def main():
    # Retrieve Environment Variables (Injected by GitHub Actions)
    github_token = os.environ.get("GITHUB_TOKEN")
    ai_model = os.environ.get("AI_MODEL", "gemini/gemini-2.5-flash")
    rules_file = os.environ.get("RULES_FILE", ".clinerules")
    active_rules_file = os.environ.get("ACTIVE_RULES_FILE", "")
    prompt_file = os.environ.get("PROMPT_FILE", "")
    output_path = os.environ.get("OUTPUT_PATH")
    exclude_patterns = os.environ.get("EXCLUDE_PATTERNS", "").split(",")
    language = os.environ.get("LANGUAGE", "ja-JP")
    strict_verify = os.environ.get("STRICT_VERIFY", "true").lower() == "true"
    status_enabled = os.environ.get("SET_COMMIT_STATUS", "true").lower() == "true"
    status_context = os.environ.get("STATUS_CONTEXT", "AI PR Reviewer")
    github_repository = os.environ.get("GITHUB_REPOSITORY")
    github_event_path = os.environ.get("GITHUB_EVENT_PATH")
    github_workspace = os.environ.get("GITHUB_WORKSPACE", "/github/workspace")

    if not all([github_token, github_repository, github_event_path]):
        print("::error::Missing required environment variables.")
        sys.exit(1)

    # Validate that an API key is provided for the selected provider
    provider = ai_model.split("/")[0] if "/" in ai_model else "openai"
    api_key_map = {
        "gemini": os.environ.get("GEMINI_API_KEY"),
        "claude": os.environ.get("ANTHROPIC_API_KEY"),
        "anthropic": os.environ.get("ANTHROPIC_API_KEY"),
        "openai": os.environ.get("OPENAI_API_KEY"),
        "gpt": os.environ.get("OPENAI_API_KEY"),
    }
    if provider in api_key_map and not api_key_map[provider]:
        print(f"::error::No API key found for provider '{provider}'. Set the corresponding secret (e.g., GEMINI_API_KEY, ANTHROPIC_API_KEY, OPENAI_API_KEY).")
        sys.exit(1)

    with open(github_event_path, "r") as f:
        event_data = json.load(f)

    if "pull_request" not in event_data:
        print("::notice::Not a pull request event. Skipping AI review.")
        sys.exit(0)

    pr_number = event_data["pull_request"]["number"]
    is_draft = event_data["pull_request"].get("draft", False)
    base_sha = event_data["pull_request"].get("base", {}).get("sha")
    head_sha = event_data["pull_request"].get("head", {}).get("sha")

    json_headers = make_json_headers(github_token)
    diff_headers = make_diff_headers(github_token)
    raw_headers = make_raw_headers(github_token)

    def status(state, description):
        set_commit_status(github_repository, head_sha, json_headers, state, description, status_context, status_enabled)

    def conclude_unverifiable(reason):
        """No verdict could be produced. strict_verify decides which way the gate falls.

        Fail-closed (default): a gate that opens whenever the verdict is missing has no
        force against an attacker who can cause the verdict to go missing (injection,
        format drift, outage). Set strict_verify: 'false' to fail open instead.
        """
        if strict_verify:
            print(f"::error::AI review could not produce a verdict ({reason}). Blocking (strict_verify=true).")
            status("error", f"AI review unverifiable: {reason}")
            sys.exit(1)
        print(f"::warning::AI review could not produce a verdict ({reason}). Passing (strict_verify=false).")
        status("success", f"AI review skipped: {reason}")
        sys.exit(0)

    print(f"::group::Initializing AI PR Reviewer for PR #{pr_number} (model: {ai_model})")

    # 1. Fetch Diff
    try:
        diff_content = get_pr_diff(github_repository, pr_number, diff_headers)

        # Apply ignore patterns (Exclude unwanted files from diff)
        if exclude_patterns:
            filtered_diff = []
            # Split diff by file (approximate)
            files_diff = re.split(r'^(diff --git .*)', diff_content, flags=re.MULTILINE)

            # files_diff[0] is often empty or preamble
            for i in range(1, len(files_diff), 2):
                header = files_diff[i]
                content = files_diff[i+1] if i+1 < len(files_diff) else ""

                # Extract filename from header: "diff --git a/path/to/file b/path/to/file"
                match = re.search(r'b/(.*)$', header.split('\n')[0])
                if match:
                    filename = match.group(1).strip()
                    should_exclude = any(fnmatch.fnmatch(filename, pattern.strip()) for pattern in exclude_patterns if pattern.strip())
                    if should_exclude:
                        print(f"::notice::Excluding file from review: {filename}")
                        continue

                filtered_diff.append(header + content)

            diff_content = "".join(filtered_diff)

    except Exception as e:
        print(f"::error::Failed to fetch PR diff: {e}")
        sys.exit(1)

    if not diff_content.strip():
        print("::notice::No diff found. Skipping review.")
        status("success", "No diff to review")
        sys.exit(0)

    # 2. Read review criteria from the PR base commit (self-reference cut).
    #    Without a base SHA the criteria cannot be pinned, which counts as unverifiable.
    if not base_sha:
        conclude_unverifiable("cannot determine the PR base commit for review criteria")

    rules_content, rules_src = get_base_file_content(github_repository, rules_file, base_sha, raw_headers, github_workspace)
    if rules_src in ("empty", "absent"):
        rules_content = ""
        print(f"::warning::Rules file '{rules_file}' not available from the base commit. Review will be based on general best practices.")
    else:
        print(f"::notice::Loaded rules from {rules_file} (source={rules_src})")

    # Precedents (optional): past human decisions that refine the rules. Kept in a
    # separate file so it can be upserted per topic without rewriting the constitution.
    active_rules_content = ""
    if active_rules_file:
        active_rules_content, ar_src = get_base_file_content(github_repository, active_rules_file, base_sha, raw_headers, github_workspace)
        if ar_src in ("empty", "absent"):
            active_rules_content = ""
            print(f"::warning::Precedents file '{active_rules_file}' not available from the base commit. Reviewing without precedents.")
        else:
            print(f"::notice::Loaded precedents from {active_rules_file} (source={ar_src})")

    # The prompt template is itself review criteria: a PR that waters down the prompt
    # must be reviewed with the pre-change prompt, so a repo-provided template is also
    # read from the base commit. Without a prompt there is no review (unverifiable).
    prompt_template = ""
    if prompt_file:
        prompt_template, tpl_src = get_base_file_content(github_repository, prompt_file, base_sha, raw_headers, github_workspace)
        if tpl_src in ("empty", "absent"):
            # Safe default: the bundled prompt is trusted (shipped with the action image),
            # so falling back keeps the gate running without adopting PR-controlled criteria.
            prompt_template = ""
            print(f"::warning::Prompt template '{prompt_file}' not available from the base commit. Falling back to the bundled prompt.")
        else:
            print(f"::notice::Loaded prompt template from {prompt_file} (source={tpl_src})")
    if not prompt_template:
        if not os.path.exists(BUNDLED_PROMPT_PATH):
            conclude_unverifiable("bundled prompt template missing from the action image")
        with open(BUNDLED_PROMPT_PATH, "r", encoding="utf-8") as f:
            prompt_template = f.read()

    # 3. Redact Sensitive Information
    rules_content_masked = redact_sensitive_info(rules_content)
    active_rules_masked = redact_sensitive_info(active_rules_content)
    diff_content_masked = redact_sensitive_info(diff_content)

    print("::endgroup::")

    # 4. Construct Prompt.
    #    Single-pass substitution: chained .replace() would re-scan already-substituted
    #    values, so a placeholder token inside the rules/precedents could re-inject
    #    attacker-controlled diff outside the <diff> delimiters. re.sub in one pass only
    #    touches placeholders that came from the template itself.
    placeholder_values = {
        "rules": rules_content_masked if rules_content_masked else "No specific rules provided. Use general software engineering best practices.",
        "active_rules": active_rules_masked if active_rules_masked else "(none)",
        "diff": diff_content_masked,
        "language": language,
    }
    prompt = re.sub(
        r"\{\{(rules|active_rules|diff|language)\}\}",
        lambda m: placeholder_values[m.group(1)],
        prompt_template,
    )

    # 5. Call AI API via LiteLLM
    print(f"::group::Calling AI API (model: {ai_model})")
    try:
        result_text = call_ai_with_retry(ai_model, prompt)
    except Exception as e:
        print(f"::error::{e}")
        print("::endgroup::")
        conclude_unverifiable("AI API call failed")
    print("::endgroup::")

    # 6. Parse the verdict (fail-closed).
    #    Both verdicts are matched only at the start of a line: a substring match
    #    would also hit prose *discussing* the verdict format (e.g. a review body
    #    quoting "RESULT: FAIL" in backticks), flipping a PASS into a false FAIL.
    #    Leading markdown decoration (bold/heading/quote markers) is tolerated —
    #    models drift into "**RESULT: PASS**" — but any word before RESULT still
    #    disqualifies the line, so mid-sentence quotes never match.
    #    If both anchored verdicts somehow appear, FAIL wins (err on the failing
    #    side). Anything else is unverifiable: the old "no FAIL found == pass"
    #    logic fell open on injection or format drift.
    verdict_re = r"^[ \t>#*_`-]*RESULT:\s*(?:\*|_|`)*\s*{}\b"
    is_fail = bool(re.search(verdict_re.format("FAIL"), result_text, re.MULTILINE))
    is_pass = not is_fail and bool(re.search(verdict_re.format("PASS"), result_text, re.MULTILINE))
    clean_text = re.sub(r"^[ \t>#*_`-]*RESULT:\s*(?:\*|_|`)*\s*(PASS|FAIL)[ \t*_`]*$\n?", "", result_text, flags=re.MULTILINE).strip()

    if not is_fail and not is_pass:
        # Print a short excerpt for debugging format drift. The prompt inputs were
        # already redacted, and v1 posted the full response as a PR comment anyway,
        # so a truncated excerpt in the CI log does not widen exposure.
        excerpt = result_text[:500].replace("\n", " ")
        print(f"::warning::Unparseable AI response (first 500 chars): {excerpt}")
        conclude_unverifiable("AI response did not contain an explicit RESULT: PASS / RESULT: FAIL")

    if is_fail:
        print("::warning::Violations detected by AI Reviewer.")
        if language.lower().startswith("ja"):
            comment_body = f"### 🤖 AI PR Reviewer\n\n🚨 **プロジェクトルールへの違反、またはセキュリティリスクを検知しました。**\n\n{clean_text}"
        else:
            comment_body = f"### 🤖 AI PR Reviewer\n\n🚨 **Violations or security risks detected based on project rules.**\n\n{clean_text}"
    else:
        print("::notice::AI Reviewer passed.")
        if language.lower().startswith("ja"):
            comment_body = f"### 🤖 AI PR Reviewer\n\n✅ **AIレビューを通過しました。**\n\n{clean_text}"
        else:
            comment_body = f"### 🤖 AI PR Reviewer\n\n✅ **AI Review Passed.**\n\n{clean_text}"

    try:
        post_or_update_comment(github_repository, pr_number, json_headers, comment_body)
    except Exception as e:
        print(f"::error::Failed to post comment: {e}")
        sys.exit(1)

    # 7. Export result to file if OUTPUT_PATH is specified
    if output_path:
        try:
            output_dir = os.path.dirname(output_path)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(clean_text)
            print(f"::notice::Review result exported to {output_path}")
        except Exception as e:
            print(f"::error::Failed to export review result: {e}")

    # 8. Set the commit status and exit status
    if is_fail:
        if is_draft:
            # Draft PRs are a sanctuary: review feedback is posted but nothing blocks.
            # The status is *pending*, not success — GitHub does not re-trigger
            # "synchronize" on ready_for_review, so a success here would let a failing
            # draft slip through a required check by flipping to ready. Pending keeps
            # the gate shut until a re-run after the PR is ready.
            print("::notice::PR is in Draft state. Commit status set to pending (warning only; re-run needed when ready).")
            status("pending", "FAIL (draft — warning only; re-run when ready for review)")
            sys.exit(0)
        else:
            print("::error::PR rejected by AI Reviewer.")
            status("failure", "AI review failed. Check the PR comments.")
            sys.exit(1)
    else:
        status("success", "AI review passed")
        sys.exit(0)

if __name__ == "__main__":
    main()
