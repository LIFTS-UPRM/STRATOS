#!/usr/bin/env bash
# setup-branch-protection.sh
#
# Configures branch protection on `main` for the STRATOS repository.
#
# Prerequisites:
#   - gh CLI installed and authenticated (gh auth login)
#
# Usage:
#   bash scripts/setup-branch-protection.sh
#
# What this does:
#   - Requires a pull request before any merge to main
#   - Requires at least 1 approving review
#   - Dismisses stale reviews when new commits are pushed
#   - Requires all conversations to be resolved
#   - Requires Frontend CI and Backend CI status checks to pass
#   - Blocks direct pushes to main

set -euo pipefail

REPO="LIFTS-UPRM/STRATOS"
BRANCH="main"

echo "Configuring branch protection for '${BRANCH}' on ${REPO}..."

gh api \
  --method PUT \
  "repos/${REPO}/branches/${BRANCH}/protection" \
  --header "Accept: application/vnd.github+json" \
  --field "required_status_checks[strict]=true" \
  --field "required_status_checks[contexts][]=Frontend CI" \
  --field "required_status_checks[contexts][]=Backend CI" \
  --field "enforce_admins=false" \
  --field "required_pull_request_reviews[required_approving_review_count]=1" \
  --field "required_pull_request_reviews[dismiss_stale_reviews]=true" \
  --field "required_pull_request_reviews[require_code_owner_reviews]=false" \
  --field "required_conversation_resolution=true" \
  --field "restrictions=null" \
  --field "allow_force_pushes=false" \
  --field "allow_deletions=false"

echo ""
echo "Branch protection applied successfully."
echo ""
echo "Summary of rules on '${BRANCH}':"
echo "  - Pull request required before merge"
echo "  - At least 1 approving review required"
echo "  - Stale approvals dismissed on new commits"
echo "  - All conversations must be resolved"
echo "  - Frontend CI and Backend CI must pass"
echo "  - Direct pushes blocked"
echo "  - Force pushes blocked"
echo ""
echo "Verify at: https://github.com/${REPO}/settings/branches"
