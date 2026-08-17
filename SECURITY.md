# Security policy

## Reporting

Report vulnerabilities through this repository's private GitHub Security Advisory form. Do not post bot tokens, Discord IDs, Worker secrets, transcript contents, or exploit details in a public issue.

Include the affected commit, deployment mode, reproduction steps, and impact. Remove or redact credentials from logs before attaching them.

## Credential response

If a Discord, Reddit, or Cloudflare credential is exposed, revoke it at the provider, replace the deployment secret, restart the affected service, and inspect Git history before publishing again. Deleting a value from the latest file does not remove it from earlier commits.

Security fixes target the current `main` branch.
