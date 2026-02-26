# Rainforest Dashboard — VPS Deployment Design

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deploy the UC4 Rainforest Dashboard to `https://rainforest.butscher.cloud` via Docker Hub + Traefik on the existing VPS.

**Architecture:** Build image locally → push to Docker Hub → copy compose file + .env to VPS via scp → `docker compose up -d`. Traefik (already running as `root-traefik-1`) handles HTTPS and Let's Encrypt automatically.

**Tech Stack:** Docker, Docker Hub (`swrobutsdocker/rainforest`), Traefik (`mytlschallenge` cert resolver), SSH alias `vps`.

---

## Context

### VPS state

- SSH alias: `vps` → `root@bot.butscher.cloud` with `~/.ssh/id_vps`
- Traefik: `root-traefik-1`, network `root_default`, cert resolver `mytlschallenge`
- No existing `/root/rainforest/` directory

### docker-compose.yml corrections needed

The local `UC4_Interaktive_Datenvisualisierung/webapp/docker-compose.yml` has two wrong values vs. the VPS:

| Field | Wrong (current) | Correct (VPS) |
|-------|-----------------|---------------|
| Traefik network | `traefik_default` | `root_default` |
| Cert resolver | `letsencrypt` | `mytlschallenge` |

Also change `build: .` → `image: swrobutsdocker/rainforest:latest` so the VPS pulls from Docker Hub.

### Correct docker-compose.yml (VPS version)

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

### .env (VPS copy, secrets only)

```
SUPABASE_URL=https://supabase.butscher.cloud
SUPABASE_KEY=<from local .env>
```

---

## Design Decisions

**Why Docker Hub, not build on VPS:** VPS has limited CPU/RAM. Building a 700 MB Python image on the VPS is slow and risks OOM. Pre-building locally keeps VPS deploy fast (~`docker pull` only).

**Why separate docker-compose.yml for VPS:** The local compose file uses `build: .` for local iteration. The VPS needs `image:` referencing Docker Hub. Keeping them separate avoids confusion.

**Why no port exposure:** All traffic goes through Traefik on 443. Port 8050 is internal only.
