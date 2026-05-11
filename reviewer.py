#!/usr/bin/env python3
"""
AI PR Reviewer Action
A strict, rule-based AI Pull Request Reviewer using Google AI Studio (Gemini API).
"""

import os
import sys
import re
import json
import time
import fnmatch
import requests
from google import genai
from google.genai import types

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

def get_pr_diff(repository, pr_number, headers):
    url = f"https://api.github.com/repos/{repository}/pulls/{pr_number}"
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.text

def post_or_update_comment(repository, pr_number, headers, body_text):
    url = f"https://api.github.com/repos/{repository}/issues/{pr_number}/comments"
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    comments = resp.json()

    bot_comment_id = None
    for c in comments:
        if "🤖 AI PR Reviewer" in c.get("body", ""):
            bot_comment_id = c["id"]
            break

    if bot_comment_id:
        update_url = f"https://api.github.com/repos/{repository}/issues/comments/{bot_comment_id}"
        resp = requests.patch(update_url, headers=headers, json={"body": body_text}, timeout=30)
        resp.raise_for_status()
    else:
        resp = requests.post(url, headers=headers, json={"body": body_text}, timeout=30)
        resp.raise_for_status()

# ==============================================================================
# Security Masking (Redaction)
# ==============================================================================
def redact_sensitive_info(text):
    """Mask sensitive information before sending to AI API."""
    if not text:
        return text
    # Mask values in key-value assignments, but avoid masking environment variable names in os.getenv()
    # Masking pattern: matches 'password="val"', 'secret: val', etc. but excludes common coding patterns
    text = re.sub(r'(?i)(password|secret|token|api[_-]?key|credentials)["\'\s:=]+(?!"[A-Z0-9_-]+")([^\s"\'},]+)', r'\1: [REDACTED]', text)
    # Basic redaction for internal IPs
    text = re.sub(r'\b(?:10\.|172\.(?:1[6-9]|2[0-9]|3[0-1])\.|192\.168\.)[0-9.]+\b', '[REDACTED_IP]', text)
    return text

# ==============================================================================
# Main Logic
# ==============================================================================
def main():
    # Retrieve Environment Variables (Injected by GitHub Actions)
    github_token = os.environ.get("GITHUB_TOKEN")
    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    rules_file = os.environ.get("RULES_FILE", ".clinerules")
    output_path = os.environ.get("OUTPUT_PATH")
    exclude_patterns = os.environ.get("EXCLUDE_PATTERNS", "").split(",")
    language = os.environ.get("LANGUAGE", "ja-JP")
    github_repository = os.environ.get("GITHUB_REPOSITORY")
    github_event_path = os.environ.get("GITHUB_EVENT_PATH")
    github_workspace = os.environ.get("GITHUB_WORKSPACE", "/github/workspace")

    if not all([github_token, gemini_api_key, github_repository, github_event_path]):
        print("::error::Missing required environment variables.")
        sys.exit(1)

    with open(github_event_path, "r") as f:
        event_data = json.load(f)

    if "pull_request" not in event_data:
        print("::notice::Not a pull request event. Skipping AI review.")
        sys.exit(0)

    pr_number = event_data["pull_request"]["number"]
    is_draft = event_data["pull_request"].get("draft", False)

    json_headers = make_json_headers(github_token)
    diff_headers = make_diff_headers(github_token)

    print(f"::group::Initializing AI PR Reviewer for PR #{pr_number}")

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
        sys.exit(0)

    # 2. Read Rules File from workspace
    rules_path = os.path.join(github_workspace, rules_file)
    rules_content = ""
    if os.path.exists(rules_path):
        with open(rules_path, "r", encoding="utf-8") as f:
            rules_content = f.read()
        print(f"::notice::Loaded rules from {rules_file}")
    else:
        print(f"::warning::Rules file '{rules_file}' not found. Review will be based on general best practices.")

    # 3. Redact Sensitive Information
    rules_content_masked = redact_sensitive_info(rules_content)
    diff_content_masked = redact_sensitive_info(diff_content)

    print("::endgroup::")

    # 4. Construct Prompt
    prompt = f"""You are a strict, highly skilled technical Code Reviewer.
Your task is to review the following git diff against the provided project rules and guidelines.

[PROJECT RULES]
{rules_content_masked if rules_content_masked else "No specific rules provided. Use general software engineering best practices."}

[GIT DIFF]
{diff_content_masked}

[INSTRUCTIONS]
1. Strictly verify if the changes violate any principles defined in the [PROJECT RULES].
2. Identify security risks, hardcoded secrets, architectural flaws, or rule violations.
3. If the code requires modifications, provide concrete code suggestions using GitHub's Suggested Changes format (```suggestion ... ```) so developers can easily apply them.
4. Your entire response and comments MUST be written in {language} (except for code snippets).
5. Output format:
   - If the code is perfect and compliant: Write "RESULT: PASS" on the first line, followed by a brief encouraging message.
   - If there are violations or risks: Write "RESULT: FAIL" on the first line, followed by detailed reasons and actionable suggestions.
"""

    # 5. Call Gemini API (Google AI Studio)
    print("::group::Calling Gemini API")
    
    # Retry logic for rate limits
    max_retries = 3
    retry_delay = 10 # seconds
    
    for attempt in range(max_retries):
        try:
            client = genai.Client(api_key=gemini_api_key)
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.0,
                )
            )
            result_text = response.text.strip()
            break # Success!
        except Exception as e:
            if "429" in str(e) and attempt < max_retries - 1:
                print(f"::warning::Rate limit hit (429). Retrying in {retry_delay}s... (Attempt {attempt + 1}/{max_retries})")
                time.sleep(retry_delay)
                continue
            else:
                print(f"::error::Gemini API call failed after {attempt + 1} attempts: {e}")
                sys.exit(1)

    print("::endgroup::")

    # 6. Evaluate Result and Post Comment
    is_fail = "RESULT: FAIL" in result_text
    clean_text = result_text.replace('RESULT: FAIL', '').replace('RESULT: PASS', '').strip()

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

    # 8. Set exit status
    if is_fail:
        if is_draft:
            print("::notice::PR is in Draft state. Action will pass despite violations.")
            sys.exit(0)
        else:
            print("::error::PR rejected by AI Reviewer.")
            sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()
