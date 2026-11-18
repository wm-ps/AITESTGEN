# Rotating platform secrets after the execution-worker lockdown

Until the execution worker stopped inheriting `aitestgen-secrets`, AI-generated
Playwright specs could read every key in it. Treat these as exposed and rotate
them once the new manifests are live (stage first, then prod).

1. **Add `VAULT_EXECUTION_TOKEN`** to `aitestgen-secrets` (any random string).
   Restart the `vault` pod: its bootstrap writes the `execution-read` policy
   (read on `secret/data/applications/*`, delete on `secret/metadata/applications/*` for the project purge job) and creates that token.
2. Roll out `10-execution-worker.yaml`; confirm a run still passes and
   `kubectl exec deploy/execution-worker -- env` shows no `SESSION_SECRET_KEY`,
   `ANTHROPIC_API_KEY` or root `VAULT_TOKEN`.
3. Rotate, in this order, updating `aitestgen-secrets` and restarting the
   services that use each:
   - `SESSION_SECRET_KEY` (logs every user out)
   - `ANTHROPIC_API_KEY`, `LITELLM_API_KEY`
   - Postgres password (RDS, then `POSTGRES_PASSWORD`)
   - AWS access keys (or move to IRSA/Pod Identity scoped to `AWS_S3_BUCKET`)
   - Vault root token (`VAULT_TOKEN`): create a new fixed token, update the
     Secret, restart `vault`, `api` and the other workers.
4. The target-app credentials in Vault were readable with the old root token;
   rotate the test-account passwords for onboarded apps as well.

The execution worker still holds a read-only Vault token, `DATABASE_URL`,
S3 and LLM keys, because it must call them itself. Closing that needs the
sandboxed per-run runner (Fix 3).
