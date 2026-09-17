# QA deployment on AWS (EC2 + Docker Compose + RDS PostgreSQL)

This guide deploys the Capacity Planning Platform to a single EC2 host running
Docker Compose, backed by an RDS PostgreSQL database. It is sized for **internal
QA testing**, not production.

## Architecture

```
Browser ──► EC2 (port 80, nginx) ──► /api/*  ──► backend container (uvicorn :8000) ──► RDS PostgreSQL
                                   └► /       ──► static SPA files
```

- The SPA and the API share one origin. nginx proxies `/api/*` to the backend
  and **strips the `/api` prefix** (e.g. `/api/plants` → backend `/plants`).
- The backend container is internal only; it is never exposed directly.
- On first startup the backend creates the schema and seeds reference data
  automatically (no migration step in this build).

## Prerequisites

- An EC2 instance (Amazon Linux 2023 or Ubuntu, `t3.small` is enough) with Docker
  and the Docker Compose plugin installed.
- An RDS PostgreSQL instance reachable from the EC2 instance.

## 1. Create the RDS PostgreSQL instance

- Engine: PostgreSQL (14+).
- Instance class: `db.t3.micro` is fine for QA.
- Initial database name: `planning`.
- Master username/password: your choice (used in `DATABASE_URL`).
- **Networking:** place RDS in the same VPC as the EC2 instance and attach a
  security group that allows inbound TCP **5432 only from the EC2 instance's
  security group**. Do not make RDS publicly accessible.

## 2. Prepare the EC2 host

- Security group: allow inbound **80** (and 443 if you add TLS) **only from your
  office/VPN IP range** — the app has no real login in QA (see Security below).
- Allow inbound 22 (SSH) from your admin IPs.
- Install Docker + Compose, then pull this repository onto the host.

## 3. Configure environment

From the repository root:

```bash
cp deploy/.env.example .env
# edit .env and set DATABASE_URL to the RDS endpoint, plus CORS_ORIGINS / AUTH_MODE
```

`DATABASE_URL` format:

```
postgresql+psycopg://<user>:<password>@<rds-endpoint>:5432/planning
```

## 4. Build and start

```bash
docker compose up -d --build
```

Check the containers and backend logs (schema creation + seed happen here):

```bash
docker compose ps
docker compose logs -f backend
```

## 5. Verify the deployment

```bash
# Health check (through nginx)
curl http://<ec2-host>/api/health        # -> {"status":"ok"}

# Data path proves the /api prefix strip + DB connectivity
curl http://<ec2-host>/api/plants         # -> seeded plant data
```

Then open `http://<ec2-host>/` in a browser (from an allowed IP) and confirm the
planning grid loads with seeded data.

## Security notes (read before sharing the URL)

- Auth is in **dev mode**: the backend trusts an `X-User` header and defaults to
  `admin`. There is effectively no login. Keep the site restricted to your
  office/VPN IP range via the EC2 security group.
- For HTTPS, terminate TLS at an ALB (with an ACM certificate) in front of the
  EC2 instance, or add a TLS-terminating proxy. QA over plain HTTP behind an IP
  allowlist is acceptable if that matches your policy.

## Redeploys and schema changes

- This build has **no database migrations**. It only runs
  `create_all` + seed-if-empty on startup, so it will not alter existing tables.
- If the SQLAlchemy models change, the RDS schema must be updated manually (or
  the database recreated). Plan QA data accordingly.

## Updating to a new build

```bash
git pull
docker compose up -d --build
```
