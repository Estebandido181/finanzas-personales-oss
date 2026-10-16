# Security policy

This is early-beta software for a single owner per self-hosted instance.
Only the latest published beta snapshot is intended for fixes; no support SLA
or independent security certification is claimed.

## Reporting

Use GitHub's private vulnerability reporting feature on the repository Security
tab when enabled. If it is unavailable, open an issue asking for a private
reporting channel, without exploit details, credentials or financial records.
The maintainer will arrange a private channel. Do not post sensitive material
in public issues or pull requests.

## Boundaries and known limitations

- Gmail authorization uses gmail.readonly, which grants mailbox reading access.
  Filtering for bank senders is application behavior, not a restriction on a
  stolen token. Each installation uses its own OAuth client/token.
- Session cookies are signed and last seven days. Logging out removes the
  browser cookie, but a saved copy remains valid until expiration. Rotate
  SESSION_SECRET and restart the application to invalidate all sessions;
  changing the password alone does not invalidate signed cookies.
- Rate limits and previews are stored in process memory. Use one application
  worker; restarts discard this state. This is not a multi-user hosted service.
- SQLite databases and backups contain sensitive derived financial data and
  are not encrypted by this application. Protect the host, storage and backups.
- Never expose scripts/servidor_e2e.py to a network or use it with private data.
  Its credentials and reset routes are deliberately public for local testing.
- Do not run untrusted public PR code on a persistent self-hosted runner or with
  production credentials. The distributed workflow uses GitHub-hosted runners
  with read-only repository permissions and no custom secrets.

Parser results are limited by supported banking formats. Review ambiguous
matches and check balances against your own bank records before relying on them.
If a credential is exposed, revoke/rotate it first; deleting a Git file alone
will not revoke it or remove older copies.
