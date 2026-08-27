# Deploy on TrueNAS SCALE

This guide targets TrueNAS SCALE 24.10 or newer, where Custom Apps use Docker
Compose. The deployment runs one dashboard container and one PostgreSQL
container. PostgreSQL data is stored in a ZFS dataset, while application code is
delivered as an immutable image from GitHub Container Registry (GHCR).

## What changes from local development

Local development runs Flask directly on the Mac and exposes PostgreSQL from
Docker. TrueNAS instead runs both pieces as containers:

```text
HTTPS hostname -> reverse proxy -> TrueNAS port 18000 -> dashboard:8000
                                                        |
                                                        +-> database:5432
                                                            |
                                                            +-> ZFS dataset
```

The image starts Gunicorn with exactly one worker because APScheduler is
embedded in the web process. The entrypoint applies committed database
migrations before Gunicorn starts. PostgreSQL is not published to the LAN.

## Prerequisites

- TrueNAS SCALE 24.10 or newer with an Apps pool configured
- a ZFS pool name, used below as `POOL`
- this project in a GitHub repository
- an HTTPS hostname that reaches a reverse proxy in front of TrueNAS port 18000
- Google OAuth credentials for that hostname

Do not publish `.env`, Google secrets, database passwords, or Flask secrets.

## 1. Publish the container image

Publishing the source code does **not** publish an image. The included
`.github/workflows/container.yml` is manual-only and requires an explicit
approval checkbox. Container image validation is still pending; do not treat
this template as a verified TrueNAS deployment yet.

When you are ready to publish a tested image, open **Actions -> Publish container
image (manual) -> Run workflow**, select `main`, and check the approval box.
This uploads AMD64 and ARM64 image packages to GHCR; it does not host a website.

The resulting image is:

```text
ghcr.io/askingrouge/home-lab-dashboard:latest
```

If the GHCR package is private, either make only the package public from its
GitHub package settings or configure registry credentials in TrueNAS. Never put
a GitHub token directly in the Compose YAML.

## 2. Create persistent storage

In TrueNAS, open **Datasets** and create these datasets beneath the desired
pool:

```text
POOL/apps/home-lab-dashboard
POOL/apps/home-lab-dashboard/postgres
```

The path used by Compose is:

```text
/mnt/POOL/apps/home-lab-dashboard/postgres
```

Replace `POOL` with the real pool name. The official PostgreSQL image initializes
the empty directory on first start. Do not store PostgreSQL data on an SMB or NFS
mount.

## 3. Choose an HTTPS hostname

Google OAuth for a server deployment needs a stable HTTPS callback. Put a
reverse proxy such as Caddy, Traefik, or Nginx Proxy Manager in front of:

```text
http://TRUENAS_IP:18000
```

Configure a hostname such as:

```text
https://monitor.example.com
```

The hostname can remain private through local DNS, a VPN, or Tailscale, but the
browser must trust its TLS certificate. Do not expose the dashboard directly to
the public internet merely to make OAuth work.

In Google Auth Platform, add this exact authorized redirect URI to the existing
Web application client:

```text
https://monitor.example.com/auth/callback
```

The Compose `GOOGLE_OAUTH_REDIRECT_URI` must match it exactly.

## 4. Generate production secrets

Generate two different values on a trusted computer:

```bash
openssl rand -hex 32
openssl rand -hex 24
```

Use the first for `CHANGE_ME_FLASK_SECRET`. Use the second for both occurrences
of `CHANGE_ME_DATABASE_PASSWORD`. Hex output is intentional because it is safe
inside both YAML and a PostgreSQL connection URL.

Keep using the existing Google client ID and client secret. Do not paste any of
these values into chat, GitHub, screenshots, or the repository.

## 5. Prepare the Compose YAML

Open `compose.truenas.yaml` in a local editor and make these replacements in a
temporary copy:

| Placeholder | Replacement |
| --- | --- |
| `POOL` | TrueNAS pool name |
| `CHANGE_ME_FLASK_SECRET` | 64-character value from the first command |
| `CHANGE_ME_DATABASE_PASSWORD` | Same database value in both places |
| `CHANGE_ME_GOOGLE_CLIENT_ID` | Google Web client ID |
| `CHANGE_ME_GOOGLE_CLIENT_SECRET` | Google client secret |
| `CHANGE_ME_HOSTNAME` | Hostname only, such as `monitor.example.com` |
| `CHANGE_ME_ADMIN_EMAIL` | Your Google email; comma-separate trusted additional admins |

The default LAN port is `18000`. Change the left side of `18000:8000` if that
port is already used. Keep the container port `8000` unchanged.

The dashboard container drops all Linux capabilities and adds back only
`NET_RAW`, which ICMP ping checks need. HTTP and TCP checks do not require that
capability.

## 6. Install the TrueNAS Custom App

1. Open **Apps -> Discover Apps**.
2. Open the three-dot menu and select **Install via YAML**.
3. Enter the name `home-lab-dashboard`.
4. Paste the completed Compose YAML into **Custom Config**.
5. Select **Save** and watch the application logs during its first start.

The database health check runs first. The dashboard then applies Alembic
migrations and starts Gunicorn. A dashboard health check triggers the embedded
scheduler after startup.

## 7. Verify the deployment

Check liveness without authentication:

```text
http://TRUENAS_IP:18000/api/health
```

It should return JSON containing `"status": "ok"`. Then browse to the HTTPS
hostname, sign in with Google, and add a reachable HTTP, TCP, or ping target.
Monitor the target by its LAN address or DNS name as seen from the TrueNAS host,
not by `localhost`.

If ping checks fail while HTTP and TCP work, confirm the deployed YAML still
contains `cap_add: [NET_RAW]`. If Google reports `redirect_uri_mismatch`, compare
the Google client entry and `GOOGLE_OAUTH_REDIRECT_URI` character for character.

## Operations

- **Update:** push code to `main`, explicitly run the manual GHCR publishing
  workflow after testing, then redeploy or update the TrueNAS Custom App so it
  pulls `latest`.
- **Migrate:** migrations run automatically before every application start.
- **Back up:** use `pg_dump` for database-consistent backups, or stop the app
  before taking a ZFS snapshot of the PostgreSQL dataset.
- **Restore:** restore PostgreSQL data only into a compatible PostgreSQL major
  version; a logical `pg_dump`/restore is safer across versions.
- **Logs:** use the TrueNAS Installed Apps screen to view the `dashboard` and
  `database` container logs.
- **Scale:** keep the dashboard at one replica until scheduling is moved into a
  dedicated worker process.
