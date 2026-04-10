# Security Policy

## Supported Versions

STRATOS is currently an in-development project and does not maintain multiple
supported release lines. Security fixes are applied to the actively maintained
development branch only.

|                    Version                    |      Supported     |
|-----------------------------------------------|--------------------|
|                    `main`                     | :white_check_mark: |
| Older branches, forks, and untagged snapshots |         :x:        |

If you need a security fix, reproduce the issue against the latest `main`
branch before reporting it.

## Reporting a Vulnerability

Please do **not** report security vulnerabilities through public GitHub issues,
pull requests, or discussions.

Use GitHub's private vulnerability reporting flow for this repository:

1. Open the repository Security tab.
2. Choose **Report a vulnerability**.
3. Include a clear description of the issue, affected components, impact, and
   reproduction steps.
4. If possible, include a minimal proof of concept and any suggested
   remediation.

What to expect after you report:

- We will aim to acknowledge receipt within 5 business days.
- We may ask follow-up questions or request validation details.
- If the report is accepted, we will work on a fix for the supported branch and
  coordinate disclosure once a patch or mitigation is ready.
- If the report is declined, we will explain why, such as the behavior being
  out of scope, unsupported, or not a security issue.

Please avoid public disclosure until the maintainers have had a reasonable
chance to investigate, prepare a fix, and coordinate release guidance.
