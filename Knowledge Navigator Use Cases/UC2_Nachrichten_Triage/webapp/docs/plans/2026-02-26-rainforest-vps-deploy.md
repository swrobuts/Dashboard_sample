# Rainforest Dashboard VPS Deployment — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deploy the UC4 Rainforest Dashboard to `https://rainforest.butscher.cloud` via Docker Hub and the existing Traefik reverse-proxy on the VPS.

**Architecture:** Fix the local `docker-compose.yml` for VPS (wrong network + cert resolver), build the Docker image, push to Docker Hub as `swrobutsdocker/rainforest:latest`, scp compose file + .env to `/root/rainforest/` on the VPS, then `docker compose up -d`.

**Tech Stack:** Docker, Docker Hub (`swrobutsdocker`), Traefik (`root_default` network, `mytlschallenge` resolver), SSH alias `vps`.

---

## Repo paths

- **UC4 webapp:** `Knowledge Navigator Use Cases/UC4_Interaktive_Datenvisualisierung/webapp/`
  (all relative paths below are from the git root `Knowledge Navigator Use Cases/`)
- **SSH alias:** `vps` (resolves to `root@bot.butscher.cloud` via `~/.ssh/id_vps`)
- **Docker Hub repo:** `swrobutsdocker/rainforest`

---

## Task 1: Fix `docker-compose.yml` for VPS

The current file has the wrong Traefik network name and cert resolver, and uses `build: .` instead of a Docker Hub image reference.

**Files:**
- Modify: `UC4_Interaktive_Datenvisualisierung/webapp/docker-compose.yml`

**Step 1: Overwrite `docker-compose.yml` with the correct VPS config**

Replace the entire file content with:

```yaml
services:
  rainforest:
    image: swrobutsdocker/rainforest:latest
    restart: unless-stopped
    env_file: .env
    labels:
      - "traefik.enable=true"
      - "traefik.docker.network=root_default"
      - "traefik.http.routers.rainforest.rule=Host(`rainforest.butscher.cloud`)"
      - "traefik.http.routers.rainforest.entrypoints=websecure"
      - "traefik.http.routers.rainforest.tls=true"
      - "traefik.http.routers.rainforest.tls.certresolver=mytlschallenge"
      - "traefik.http.routers.rainforest.tls.domains[0].main=rainforest.butscher.cloud"
      - "traefik.http.services.rainforest.loadbalancer.server.port=8050"
    networks:
      - traefik_net

networks:
  traefik_net:
    external: true
    name: root_default
```

**Step 2: Verify the diff**

```bash
cd "Knowledge Navigator Use Cases"
git diff UC4_Interaktive_Datenvisualisierung/webapp/docker-compose.yml
```

Expected changes:
- `build: .` removed, `image: swrobutsdocker/rainforest:latest` added
- `traefik_default` → `root_default` (in network section)
- `letsencrypt` → `mytlschallenge`
- Added `traefik.docker.network=root_default` label
- Added `traefik.http.routers.rainforest.tls=true` label
- Added `tls.domains[0].main` label

**Step 3: Commit**

```bash
git add UC4_Interaktive_Datenvisualisierung/webapp/docker-compose.yml
git commit -m "fix(UC4): update docker-compose for VPS — root_default network, mytlschallenge cert"
```

---

## Task 2: Build Docker image and push to Docker Hub

**Files:**
- No file changes — build + push only

**Step 1: Build the image**

```bash
cd "Knowledge Navigator Use Cases/UC4_Interaktive_Datenvisualisierung/webapp"
docker build -t swrobutsdocker/rainforest:latest .
```

Expected: build completes, final line says `Successfully tagged swrobutsdocker/rainforest:latest`.

This takes ~2–3 minutes (downloading base image + pip install).

**Step 2: Verify the image**

```bash
docker images swrobutsdocker/rainforest
```

Expected: one row, tag `latest`, size ~700 MB.

**Step 3: Push to Docker Hub**

```bash
docker push swrobutsdocker/rainforest:latest
```

Expected: layers pushed, final line `latest: digest: sha256:...`.

If not logged in, run `docker login` first with Docker Hub credentials.

---

## Task 3: Prepare VPS deployment directory

**Files:**
- Create on VPS: `/root/rainforest/docker-compose.yml`
- Create on VPS: `/root/rainforest/.env`

**Step 1: Create the directory on VPS**

```bash
ssh vps "mkdir -p /root/rainforest"
```

Expected: no output (directory created).

**Step 2: Copy docker-compose.yml to VPS**

```bash
scp "Knowledge Navigator Use Cases/UC4_Interaktive_Datenvisualisierung/webapp/docker-compose.yml" vps:/root/rainforest/docker-compose.yml
```

Expected: file transferred with no errors.

**Step 3: Create .env on VPS**

Read the values from the local `.env`:

```bash
cat "Knowledge Navigator Use Cases/UC4_Interaktive_Datenvisualisierung/webapp/.env"
```

Then create it on the VPS (replace `<VALUE>` with the actual values):

```bash
ssh vps "cat > /root/rainforest/.env << 'EOF'
SUPABASE_URL=https://supabase.butscher.cloud
SUPABASE_KEY=<from local .env>
EOF"
```

**Step 4: Verify files exist on VPS**

```bash
ssh vps "ls -la /root/rainforest/ && echo '---' && cat /root/rainforest/docker-compose.yml"
```

Expected: both `docker-compose.yml` and `.env` listed; compose file shows correct content.

---

## Task 4: Start the container on VPS and verify

**Files:**
- No file changes — runtime only

**Step 1: Pull the image on VPS and start**

```bash
ssh vps "cd /root/rainforest && docker compose pull && docker compose up -d"
```

Expected output:
```
Pulling rainforest ... done
Container rainforest  Started
```

**Step 2: Check container is running**

```bash
ssh vps "docker ps --filter name=rainforest"
```

Expected: one row, status `Up X seconds`.

**Step 3: Check Traefik picked up the router**

```bash
ssh vps "docker logs root-traefik-1 2>&1 | grep rainforest | tail -5"
```

Expected: log lines showing the `rainforest` router was added.

**Step 4: Wait for TLS certificate and verify HTTPS**

```bash
sleep 10 && curl -s -o /dev/null -w "%{http_code}" https://rainforest.butscher.cloud/
```

Expected: `200`

If `000` or SSL error, wait 30 more seconds (Let's Encrypt cert issuance takes ~10–30 s) and retry.

**Step 5: Smoke-test the dashboard**

Open `https://rainforest.butscher.cloud` in a browser. Verify:
- Dashboard loads with header "Amazon Deforestation Monitor" (or equivalent)
- KPI cards show numbers (not blank)
- Language toggle works (DE/EN/PT)
- At least one chart renders

---

## Task 5: DNS verification + cleanup

**Step 1: Confirm DNS resolves correctly**

```bash
dig +short rainforest.butscher.cloud
```

Expected: returns the VPS IP address (same as `bot.butscher.cloud`).

If DNS not yet propagated, wait a few minutes and retry.

**Step 2: Verify certificate is valid (not self-signed)**

```bash
curl -vI https://rainforest.butscher.cloud/ 2>&1 | grep -E "SSL|subject|issuer|expire"
```

Expected: `Let's Encrypt` as issuer, valid expiry date.

**Step 3: Remove the old local Docker image (optional cleanup)**

```bash
docker image rm rainforest-dashboard:latest 2>/dev/null || true
```

This removes the old locally-tagged image; the Docker Hub image stays.
