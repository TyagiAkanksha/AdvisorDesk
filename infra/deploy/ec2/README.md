# EC2 host — recreate-from-scratch (IaC-lite)

WR-14: the production host was hand-built. This directory captures the reproducible pieces so it can
be recreated without archaeology. The live resource IDs (instance, EIP, SG, VPC/subnet) live in the
gitignored ledger (`.superpowers/sdd/progress.md`); this doc is the *spec*, not the live inventory.

Files:
- `user-data.sh` — the instance boot script (installs docker + the compose plugin, enables the SSM
  agent, creates `/opt/advisordesk`). Verbatim from the running instance; contains no secrets.
- `iam-ssm-read-policy.json` — the inline policy `advisordesk-ssm-read` on the instance role
  (scoped SSM read of `/advisordesk/*` + `kms:Decrypt` via SSM only).

## Recreate procedure

1. **IAM role + instance profile** — role `advisordesk-ec2-role` with:
   - managed: `AmazonSSMManagedInstanceCore`, `AmazonEC2ContainerRegistryReadOnly`
   - inline: `advisordesk-ssm-read` (this dir's JSON)
   - instance profile `advisordesk-ec2-profile` wrapping the role.
2. **Security group** `advisordesk-web` — inbound **tcp/80** and **tcp/443** from `0.0.0.0/0` only
   (no SSH; management is SSM Session Manager). All egress allowed (default).
3. **Instance** — Amazon Linux 2023, x86_64, **t3.small**, 20 GB gp3, the IAM instance profile above,
   the SG above, in the default VPC; attach `user-data.sh` as user data. Pin desired=1 (in-memory
   rate limiter + metrics require a single instance — see `../prod/docker-compose.yml` and PRD §9).
4. **Elastic IP** — allocate + associate; point the three Cloudflare DNS records
   (`advisordesk`, `admin.advisordesk`, `api.advisordesk`) at it, **grey-cloud (DNS-only)**.
5. **SSM parameters** — create `/advisordesk/{DATABASE_URL, OPENAI_API_KEY, SESSION_SECRET,
   GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET}` as SecureString and `/advisordesk/ADMIN_EMAILS` as String
   (owner-supplied values; never committed). See `../env-checklist.md`.
6. **App bring-up** — stage `../prod/{docker-compose.yml, Caddyfile, fetch-secrets.sh}` into
   `/opt/advisordesk/`, then (via SSM): `./fetch-secrets.sh` → ECR login → `docker compose up -d`.
   Caddy obtains Let's Encrypt certs once DNS resolves. Then run `../VERIFY.md`.

## Not yet automated (deferred)

Full Terraform/CDK is out of scope for this single-host dev deployment. If the host churns often,
promote this to Terraform. Backups: the datastore is managed Supabase (its own PITR); the host is
stateless apart from Caddy's cert volume, which re-issues on recreate.
