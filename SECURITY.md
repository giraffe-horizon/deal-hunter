# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 1.0.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability in Deal Hunter, please report it responsibly.

**Do NOT open a public GitHub issue for security vulnerabilities.**

Instead, please email the maintainers or use [GitHub's private vulnerability reporting](https://github.com/giraffe-horizon/deal-hunter/security/advisories/new).

### What to include

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

### Response timeline

- **Acknowledgement:** within 48 hours
- **Initial assessment:** within 7 days
- **Fix release:** best effort, typically within 30 days for confirmed vulnerabilities

### Scope

The following are in scope:

- Command injection via profile YAML
- Credential leakage (API tokens, secrets)
- Arbitrary file read/write
- Dependency vulnerabilities with known exploits

The following are out of scope:

- Scraping target websites blocking or rate-limiting the tool
- Denial of service against the local CLI tool
- Issues requiring physical access to the machine
