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

3. **GCS bucket**: Create a bucket (e.g. in `europe-west9`). Set `STORAGE_BACKEND=gcs`, `GCS_BUCKET_NAME`, and `GCS_PROJECT_ID` in `.env.staging.gcp`. Objects live under `GCS_DOCUMENTS_PREFIX` (default `world-skills`) with per-upload folders from the app keys (`cycles/...`, `consent/...`, `submissions/...`, `imports/...`). To migrate existing local files from a dev machine, use [`scripts/migrate-storage-to-gcs.sh`](scripts/migrate-storage-to-gcs.sh). With `STORAGE_BACKEND=gcs`, the backend uses `GcsObjectStorage` (ADC on the VM, or `GCS_CREDENTIALS_PATH` if set).

4. **Firewall** (from your workstation, with `gcloud` configured):

   ```bash
   export GCP_PROJECT_ID=your-project-id
   export VM_NETWORK_TAGS=world-skills-staging
   ./gcp/staging/infrastructure/firewall-rules.sh
   ```

5. **VM bootstrap**: SSH in and run `./gcp/staging/infrastructure/scripts/setup-gce-vm.sh` (or install Docker + Compose manually).

6. **Cloud SQL**: Create a PostgreSQL instance and database/user for world-skills. Note the **connection name** `project:region:instance`.

7. **DNS**: Point `A`/`AAAA` records for these hosts at the VM’s external IP:

   | Role | Host |
   |------|------|
   | SPA | `worldskills.jamesyin.com` |
   | SPA | `worldskills.ctvet.gov.gh` |
   | API | `worldskills-api.jamesyin.com` |
   | API | `worldskills-api.ctvet.gov.gh` |
   | Traefik dashboard | `traefik-worldskills-staging.jamesyin.com` |

   Host rules live in [`traefik/dynamic.staging.yml`](../../traefik/dynamic.staging.yml); the dashboard Host is a Traefik label in [`compose.staging.gcp.yaml`](../../compose.staging.gcp.yaml).

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

`prestart.sh` runs **Alembic migrations** and **initial super admin** when the backend container starts.

## Frontend API URL

Staging does **not** bake `NEXT_PUBLIC_API_BASE_URL`. The browser derives `worldskills-api.<parent>` from the SPA host in `frontend/lib/api.ts`. SSR inside the container uses `INTERNAL_API_BASE_URL`.

## Frontend build note

- If frontend Docker builds log `[baseline-browser-mapping] The data in this module is over two months old`, prefer upgrading `next` and `eslint-config-next` to the latest stable minor first.
- Running `npm i baseline-browser-mapping@latest -D` alone may not clear the warning on some `16.0.x` Next.js builds.

## Related documentation

- Sibling project GCP staging docs (if present) for Cloud SQL proxy / service-account patterns
