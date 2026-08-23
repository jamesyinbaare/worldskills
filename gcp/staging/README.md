# GCP staging deployment (world-skills)

Dedicated GCE VM running Docker Compose: **Traefik** (TLS), **FastAPI backend**, **Next.js frontend**, and **Cloud SQL Auth Proxy**.

## Layout

```
gcp/staging/
├── README.md
├── scripts/
│   ├── deploy.sh
│   ├── setup-secrets.sh
│   ├── migrate-storage-to-gcs.sh
│   ├── verify-https-security.sh
│   └── fix-traefik-404.sh
└── infrastructure/
    ├── firewall-rules.sh
    └── scripts/
        └── setup-gce-vm.sh
```

Root files:

- [`compose.staging.gcp.yaml`](../../compose.staging.gcp.yaml) — staging compose
- [`traefik/`](../../traefik/) — Traefik static + dynamic config
- [`.env.staging.gcp.example`](../../.env.staging.gcp.example) — environment template

## Quick start

1. **GCP**: Create or reuse a project; enable Compute Engine, Cloud SQL (PostgreSQL), **Cloud Storage**, and Secret Manager as needed.

2. **VM**: Create an Ubuntu 22.04 VM (e.g. `e2-medium`), attach a service account with **`roles/cloudsql.client`**, **`roles/storage.objectAdmin`** (or `objectCreator` + `objectViewer` if you tighten IAM), and Secret Manager access if you use it. Tag the VM `world-skills-staging` for firewall rules.

   **Access scopes (required for Cloud SQL Auth Proxy):** set the VM to **Allow full access to all Cloud APIs** (`cloud-platform`). IAM roles alone are not enough — narrow scopes cause proxy errors like `ACCESS_TOKEN_SCOPE_INSUFFICIENT` / `403` on `sqladmin.googleapis.com`. Changing scopes requires stopping the VM, updating scopes, then starting it. Verify on the VM:

   ```bash
   curl -s -H "Metadata-Flavor: Google" \
     http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/scopes
   ```

   You should see `https://www.googleapis.com/auth/cloud-platform`.

3. **GCS bucket**: Create a bucket (e.g. in `europe-west9`). Set `STORAGE_BACKEND=gcs`, `GCS_BUCKET_NAME`, and `GCS_PROJECT_ID` in `.env.staging.gcp`. Objects live under `GCS_DOCUMENTS_PREFIX` (default `world-skills`) with per-upload folders from the app keys (`cycles/...`, `consent/...`, `submissions/...`, `imports/...`). To migrate existing local files from a dev machine, use [`scripts/migrate-storage-to-gcs.sh`](scripts/migrate-storage-to-gcs.sh). With `STORAGE_BACKEND=gcs`, the backend uses `GcsObjectStorage` (ADC on the VM, or `GCS_CREDENTIALS_PATH` if set).

4. **Firewall** (from your workstation, with `gcloud` configured):

   ```bash
   export GCP_PROJECT_ID=your-project-id
   export VM_NETWORK_TAGS=world-skills-staging
   ./gcp/staging/infrastructure/firewall-rules.sh
   ```

5. **VM bootstrap**: SSH in and run `./gcp/staging/infrastructure/scripts/setup-gce-vm.sh` (or install Docker + Compose manually).

6. **Cloud SQL**: Create a PostgreSQL instance and database/user for world-skills, **or** reuse a shared instance (another product’s Cloud SQL) with a **separate database** for world-skills. Set `CLOUD_SQL_CONNECTION_NAME` to `project:region:instance`. Set `DATABASE_URL` to the world-skills database name on that instance (host `cloud-sql-proxy`). When sharing an instance, keep pools small (`POOL_SIZE` / `MAX_OVERFLOW`, e.g. 5/5) so both apps stay under Cloud SQL `max_connections`.

7. **DNS**: Point `A`/`AAAA` records for these hosts at the VM’s external IP:

   | Role | Host | Notes |
   |------|------|-------|
   | SPA | `worldskills.jamesyin.com` | Required |
   | API | `worldskills-api.jamesyin.com` | Required |
   | SPA | `worldskills.ctvet.gov.gh` | Active when DNS A/AAAA points at the VM |
   | API | `worldskills-api.ctvet.gov.gh` | Active when DNS A/AAAA points at the VM |
   | Traefik dashboard | `traefik-worldskills-staging.jamesyin.com` | Optional |

   Host rules live in [`traefik/dynamic.staging.yml`](../../traefik/dynamic.staging.yml); the dashboard Host is a Traefik label in [`compose.staging.gcp.yaml`](../../compose.staging.gcp.yaml). **Do not** put undeployed DNS names on the same Traefik router as live hosts — ACME will fail for the whole bundle and browsers will reject API calls.

8. **Secrets** (optional): `./gcp/staging/scripts/setup-secrets.sh` — or place values only in `.env.staging.gcp`.

9. **Configure**:

   ```bash
   cp .env.staging.gcp.example .env.staging.gcp
   # Edit DATABASE_URL, SECRET_KEY, GCS_*, CORS_ORIGINS, FRONTEND_BASE_URL,
   # SUPER_ADMIN_*, CLOUD_SQL_CONNECTION_NAME
   ```

10. **Deploy** (on the VM, repo root = `world-skills`):

   ```bash
   chmod +x gcp/staging/scripts/deploy.sh
   ./gcp/staging/scripts/deploy.sh
   ```

`prestart.sh` runs **Alembic migrations** and **initial super admin** when the backend container starts. On a fresh or half-failed migrate (e.g. after a failed `upgrade`), reset the empty staging database (drop app schema / recreate DB) before re-deploying — do not `alembic stamp head` without applying revisions.

### DB / proxy troubleshooting

Symptoms: `/health` is 200 but `/settings`, `/auth/register`, etc. hang or fail with `TimeoutError`, `ConnectionDoesNotExistError`, or `Temporary failure in name resolution`. Proxy logs show `Accepted connection` then `instance closed the connection`.

1. Confirm DNS inside the backend container: `getent hosts cloud-sql-proxy`.
2. Confirm `DATABASE_URL` uses host `cloud-sql-proxy` and the **world-skills** database/user (not the other product’s DB name on a shared instance).
3. Test auth through the proxy (replace user/password/db):

   ```bash
   docker run --rm --network world-skills-network-staging postgres:16 \
     psql "postgresql://USER:PASSWORD@cloud-sql-proxy:5432/WORLD_SKILLS_DB" -c 'SELECT current_database(), now();'
   ```

4. Check Cloud SQL connection count / `max_connections` if both apps share the instance.
5. After fixing env, recreate proxy + backend:  
   `docker compose -f compose.staging.gcp.yaml up -d --force-recreate cloud-sql-proxy world-skills-backend`
6. Prefer `/ready` (runs `SELECT 1`) for deploy/smoke checks that the API can serve traffic. Docker **liveness** uses `/health` only (see below).

### API hung / SPA loads but login fails

Symptoms: SPA returns 200; `https://worldskills-api…/health` times out; backend container shows `unhealthy` but stays up.

Cause: single-worker FastAPI event loop wedged. Compose `restart: unless-stopped` does **not** recycle on failed healthchecks.

Mitigations in [`compose.staging.gcp.yaml`](../../compose.staging.gcp.yaml):

1. Backend healthcheck probes **`/health`** (no DB) every 15s.
2. Backend has label `autoheal=true`; the **`autoheal`** service restarts labeled containers when healthchecks fail.
3. Request logging uses pure ASGI middleware (not Starlette `BaseHTTPMiddleware`) to avoid known hang modes.

Manual recovery if needed:

```bash
docker compose --env-file .env.staging.gcp -f compose.staging.gcp.yaml \
  up -d --force-recreate world-skills-backend
```

## Frontend API URL

Staging bakes `NEXT_PUBLIC_API_BASE_URL` (default `https://worldskills-api.jamesyin.com`) at frontend image build via compose build args. When unset, the browser still derives `worldskills-api.<parent>` from the SPA host in `frontend/lib/api.ts`. SSR inside the container uses `INTERNAL_API_BASE_URL`.

## TLS / Let's Encrypt

Traefik routers are **one Host per router** in [`traefik/dynamic.staging.yml`](../../traefik/dynamic.staging.yml). Bundling `jamesyin.com` and `ctvet.gov.gh` in a single `Host() || Host()` rule makes ACME request a SAN certificate for both; if either domain is NXDOMAIN, **neither** gets a cert and Traefik serves `TRAEFIK DEFAULT CERT` (browsers then block API `fetch` → competitions/login fail).

Active staging routes cover `worldskills(.|-api).jamesyin.com` and `worldskills(.|-api).ctvet.gov.gh`. If ctvet DNS is removed, drop those routers (keep a copy in [`traefik/dynamic.staging.ctvet.snippet.yml`](../../traefik/dynamic.staging.ctvet.snippet.yml)) and recreate Traefik so ACME does not fail for the remaining hosts.

## Frontend build note

- If frontend Docker builds log `[baseline-browser-mapping] The data in this module is over two months old`, prefer upgrading `next` and `eslint-config-next` to the latest stable minor first.
- Running `npm i baseline-browser-mapping@latest -D` alone may not clear the warning on some `16.0.x` Next.js builds.

## Build performance

`deploy.sh` builds images **on the VM** with BuildKit enabled (`DOCKER_BUILDKIT=1`), builds **before** `compose down` (old stack stays up during compile), and uses `docker compose build --parallel`.

Frontend/backend `.dockerignore` files keep `node_modules`, `.next`, and `.venv` out of the build context. The frontend image skips Playwright/Vitest/ESLint during `npm ci` and uses an npm BuildKit cache mount; the backend uses a uv cache mount.

Cold (first) builds are still slow — especially Next.js on a small VM. For faster compiles, prefer **`e2-standard-4`** (or larger) over `e2-medium`. Repeat deploys with unchanged lockfiles should reuse npm/uv cache layers.

Larger follow-up if deploy time is still too high: build/push images in CI to Artifact Registry and `pull` on the VM instead of compiling on-box.

## Related documentation

- Sibling project GCP staging docs (if present) for Cloud SQL proxy / service-account patterns
