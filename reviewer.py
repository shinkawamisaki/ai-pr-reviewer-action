#!/usr/bin/env python3
"""
AI PR Reviewer Action
A strict, rule-based AI Pull Request Reviewer using Google AI Studio (Gemini API).
"""

import os
import sys
import re
import json
import requests
from google import genai
from google.genai import types

# ==============================================================================
# Retrieve Environment Variables (Injected by GitHub Actions)
# ==============================================================================
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
RULES_FILE = os.environ.get("RULES_FILE", ".clinerules")
OUTPUT_PATH = os.environ.get("OUTPUT_PATH")

# GitHub Actions exposes these automatically
GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY")
GITHUB_EVENT_PATH = os.environ.get("GITHUB_EVENT_PATH")
GITHUB_WORKSPACE = os.environ.get("GITHUB_WORKSPACE", "/github/workspace")

if not all([GITHUB_TOKEN, GEMINI_API_KEY, GITHUB_REPOSITORY, GITHUB_EVENT_PATH]):
    print("::error::Missing required environment variables.")
    sys.exit(1)

# Parse event payload to get PR information
with open(GITHUB_EVENT_PATH, "r") as f:
    event_data = json.load(f)

if "pull_request" not in event_data:
    print("::notice::Not a pull request event. Skipping AI review.")
    sys.exit(0)

PR_NUMBER = event_data["pull_request"]["number"]
COMMIT_SHA = event_data["pull_request"]["head"]["sha"]
IS_DRAFT = event_data["pull_request"].get("draft", False)

# ==============================================================================
# GitHub API Helpers
# ==============================================================================
GH_HEADERS_JSON = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28"
}

GH_HEADERS_DIFF = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3.diff",
    "X-GitHub-Api-Version": "2022-11-28"
}

def get_pr_diff():
    url = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/pulls/{PR_NUMBER}"
    resp = requests.get(url, headers=GH_HEADERS_DIFF)
    resp.raise_for_status()
    return resp.text

def post_or_update_comment(body_text):
    url = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/issues/{PR_NUMBER}/comments"
    resp = requests.get(url, headers=GH_HEADERS_JSON)
    resp.raise_for_status()
    comments = resp.json()
    
    bot_comment_id = None
    for c in comments:
        # Identify previous comments made by this action
        if "🤖 AI PR Reviewer" in c.get("body", ""):
            bot_comment_id = c["id"]
            break
            
    if bot_comment_id:
        update_url = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/issues/comments/{bot_comment_id}"
        requests.patch(update_url, headers=GH_HEADERS_JSON, json={"body": body_text})
    else:
        requests.post(url, headers=GH_HEADERS_JSON, json={"body": body_text})

# ==============================================================================
# Security Masking (Redaction)
# ==============================================================================
def redact_sensitive_info(text):
    """Mask sensitive information before sending to AI API."""
    if not text:
        return text
    # Basic redaction for secrets, passwords, tokens
    text = re.sub(r'(?i)(password|secret|token|api[_-]?key|credentials)["\'\s:=]+[^\s"\'},]+', r'\1: [REDACTED]', text)
    # Basic redaction for internal IPs
    text = re.sub(r'\b(?:10\.|172\.(?:1[6-9]|2[0-9]|3[0-1])\.|192\.168\.)[0-9.]+\b', '[REDACTED_IP]', text)
    return text

# ==============================================================================
# Main Logic
# ==============================================================================
def main():
    print(f"::group::Initializing AI PR Reviewer for PR #{PR_NUMBER}")
    
    # 1. Fetch Diff
    try:
        diff_content = get_pr_diff()
    except Exception as e:
        print(f"::error::Failed to fetch PR diff: {e}")
        sys.exit(1)
        
    if not diff_content.strip():
        print("::notice::No diff found. Skipping review.")
        sys.exit(0)

    # 2. Read Rules File from workspace
    rules_path = os.path.join(GITHUB_WORKSPACE, RULES_FILE)
    rules_content = ""
    if os.path.exists(rules_path):
        with open(rules_path, "r", encoding="utf-8") as f:
            rules_content = f.read()
        print(f"::notice::Loaded rules from {RULES_FILE}")
    else:
        print(f"::warning::Rules file '{RULES_FILE}' not found. Review will be based on general best practices.")

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
4. Your entire response and comments MUST be written in Japanese (except for code snippets).
5. Output format:
   - If the code is perfect and compliant: Write "RESULT: PASS" on the first line, followed by a brief encouraging message.
   - If there are violations or risks: Write "RESULT: FAIL" on the first line, followed by detailed reasons and actionable suggestions.
"""

    # 5. Call Gemini API (Google AI Studio)
    print("::group::Calling Gemini API")
    try:
        # Using the new google-genai client
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.0, # Deterministic output
            )
        )
        result_text = response.text.strip()
    except Exception as e:
        print(f"::error::Gemini API call failed: {e}")
        sys.exit(1)
        
    print("::endgroup::")

    # 6. Evaluate Result and Post Comment
    is_fail = "RESULT: FAIL" in result_text
    clean_text = result_text.replace('RESULT: FAIL', '').replace('RESULT: PASS', '').strip()
    
    if is_fail:
        print("::warning::Violations detected by AI Reviewer.")
        comment_body = f"### 🤖 AI PR Reviewer\n\n🚨 **プロジェクトルールへの違反、またはセキュリティリスクを検知しました。**\n\n{clean_text}"
    else:
        print("::notice::AI Reviewer passed.")
        comment_body = f"### 🤖 AI PR Reviewer\n\n✅ **AIレビューを通過しました。**\n\n{clean_text}"
    
    post_or_update_comment(comment_body)

    # 7. Export result to file if OUTPUT_PATH is specified
    if OUTPUT_PATH:
        try:
            # Create directory if it doesn't exist
            output_dir = os.path.dirname(OUTPUT_PATH)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir, exist_ok=True)
            
            with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
                f.write(clean_text)
            print(f"::notice::Review result exported to {OUTPUT_PATH}")
        except Exception as e:
            print(f"::error::Failed to export review result: {e}")

    # 8. Set exit status
    if is_fail:
        if IS_DRAFT:
            print("::notice::PR is in Draft state. Action will pass despite violations.")
            sys.exit(0)
        else:
            print("::error::PR rejected by AI Reviewer.")
            sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()
