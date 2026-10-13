# Security boundaries

Trusted-local execution is explicitly unsandboxed. Use it only for code the operator owns and has reviewed. Docker reduces exposure through network disabling, read-only source mounts, non-root identity and resource restrictions, but is not a VM boundary for hostile code. Tests can lie about their results; verdicts are regression evidence, not adversarial attestation.

The tool does not mount the source checkout into its containers. It mounts disposable Git snapshots and one writable results directory. JUnit reading refuses symlinks and non-regular or oversized files. Reports contain selected source/test output and should be reviewed before sharing. The optional Claude adapter sends only explicitly selected input files after opt-in and stores no API key. It never executes generated code.

## Reporting a vulnerability

Use [GitHub private vulnerability reporting](https://github.com/Balaji91221/patchproof/security/advisories/new) to contact the maintainers. Include the affected version, a sanitized
reproduction, and the expected and observed behavior. Do not post secrets,
credentials, or sensitive exploit details in public issues.

Security fixes target the latest development release (currently 0.2.0).
Older releases have no maintenance guarantee. No independent security
audit or response-time guarantee is claimed.
