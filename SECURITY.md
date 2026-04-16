# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | Yes       |

## Reporting a Vulnerability

If you discover a security vulnerability in BlueRock, please report it responsibly:

**Email:** support@bluerock.io

**GitHub Security Advisories:** [Report a vulnerability](https://github.com/bluerock-io/bluerock/security/advisories/new)

Please include:

- A clear description of the issue and its potential impact
- Steps to reproduce or proof-of-concept
- Affected versions or commit identifiers
- Any known workarounds
- Desired attribution (name or handle)

### What to expect

- **Acknowledgment** within 72 hours
- **Assessment and fix** within 30 days for confirmed vulnerabilities
- **Credit** in the security advisory (unless you prefer anonymity)

### Scope

BlueRock's security scope covers:
- The Python sensor (`bluerock` package) -- hook modules, CLI, config loading
- The Rust DSO backend (`bluerock-oss` package) -- event writing, spool management
- CI/CD pipeline security -- supply chain, action pinning, OIDC publishing

Out of scope:
- Vulnerabilities in monitored applications (BlueRock observes, it does not protect)
- Third-party dependencies (report to the upstream project)

### Disclosure

We follow [coordinated vulnerability disclosure](https://en.wikipedia.org/wiki/Coordinated_vulnerability_disclosure). Please do not file public issues for security vulnerabilities.
