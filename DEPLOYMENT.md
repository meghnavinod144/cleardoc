# Deployment runbook — Azure Web App for Containers

The scripted path for tonight's deploy. Prerequisite: Azure subscription
active (signup step 3 complete).

## 0. One-time: make the container image public

GitHub → your profile → Packages → `cleardoc` → Package settings →
Danger Zone → Change visibility → Public. (Azure then pulls it with no
credentials.)

## 1. Create the Web App (Azure Portal)

Portal → Create a resource → **Web App**:

- Subscription: Azure subscription 1 · Resource group: new, `cleardoc-rg`
- Name: `cleardoc-<something-unique>` → becomes `https://<name>.azurewebsites.net`
- Publish: **Container** · OS: Linux · Region: Central India
- Pricing plan: **F1 (Free)** — fine for a portfolio app
- Container tab → Image source: *Other container registries* →
  Server URL `https://ghcr.io` · Image and tag
  `meghnavinod144/cleardoc:latest` · Port `8000`
- Review + create → Create (first boot takes a few minutes)

## 2. Configuration (Web App → Settings → Environment variables)

| Name | Value |
| --- | --- |
| `GEMINI_API_KEY` | the Gemini key |
| `CLEARDOC_SECRET` | a long random string (JWT signing) |
| `WEBSITES_PORT` | `8000` |

Save → app restarts with the real brain on.

## 3. Smoke test

- `https://<name>.azurewebsites.net/health` → `{"status":"ok", ...}`
- Sign up in the UI, upload `data/sample_bill.png`, ask a question —
  expect a real Gemini answer with citations.

## 4. Guardrails (same visit)

- Cost alert: Subscription → Cost Management → Budgets → new budget
  (e.g. $5/month) with an email alert at 80%.
- Note: SQLite on App Service free tier is ephemeral (resets on restart)
  — acceptable for the demo; the PostgreSQL migration is the documented
  next step (`database.py` is already one-URL-change ready).

## Later (not tonight)

- PostgreSQL (Azure Database for PostgreSQL flexible server) + pgvector
- Custom domain + the PWA install banner (needs stable HTTPS domain ✓)
- CD: GitHub Actions deploy step so every green push ships automatically
