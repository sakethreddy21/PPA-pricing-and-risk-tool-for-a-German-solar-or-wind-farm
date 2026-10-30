# Production Deployment Guide: German PPA Pricing & Risk Engine

This project is built for production deployment across multiple environments:
1. **Containerized Deployment (Docker & Docker Compose)**
2. **Cloud Serverless: Vercel (Next.js) + Railway / Render / Fly.io (FastAPI)**
3. **Single Linux Server / VPS (Ubuntu, Debian, macOS)**

---

## Architecture Overview

```
                      ┌───────────────────────────────┐
                      │    Client Browser / User      │
                      └──────────────┬────────────────┘
                                     │
                 ┌───────────────────┴───────────────────┐
                 │                                       │
                 ▼                                       ▼
    ┌─────────────────────────┐             ┌─────────────────────────┐
    │   Next.js Frontend      │   HTTP      │     FastAPI Backend     │
    │   Port 3000 (React)     ├────────────►│     Port 8000 (Python)    │
    └─────────────────────────┘             └────────────┬────────────┘
                                                         │
                                                         ▼
                                            ┌─────────────────────────┐
                                            │ DuckDB Columnar Storage │
                                            │  (data/ppa_market.db)   │
                                            └─────────────────────────┘
```

---

## Option 1: Docker Compose (Recommended for VPS / Cloud VMs)

Run both the frontend and backend containers with a single command:

```bash
# 1. Clone the repository
git clone <your-repo-url>
cd "PPA pricing and risk tool for a German solar or wind farm"

# 2. Build and start containers in the background
docker-compose up -d --build

# 3. Verify services are running
docker-compose ps
```

* **Frontend**: `http://<your-server-ip>:3000`
* **Backend API Docs**: `http://<your-server-ip>:8000/docs`
* **Health Check**: `http://<your-server-ip>:8000/api/health`

To view container logs:
```bash
docker-compose logs -f
```

---

## Option 2: Cloud Deployment (Vercel + Railway / Render)

### A. Deploy FastAPI Backend on Railway or Render
1. Connect your GitHub repository to **[Railway.app](https://railway.app)** or **[Render.com](https://render.com)**.
2. Select **Docker Deployment** using `Dockerfile.api` (or Python web service with build command `pip install -r requirements.txt` and start command `uvicorn api.main:app --host 0.0.0.0 --port $PORT`).
3. Set Environment Variables:
   * `PORT`: `8000` (or leave default on Render)
   * `PYTHONUNBUFFERED`: `1`
   * *(Optional)* `ENTSOE_API_TOKEN`: Your ENTSO-E Transparency API key.
4. Copy your deployed backend public URL (e.g. `https://ppa-api-production.up.railway.app`).

### B. Deploy Next.js Frontend on Vercel
1. Import the repository on **[Vercel](https://vercel.com)**.
2. Set the **Root Directory** to `frontend`.
3. Add Environment Variable:
   * `NEXT_PUBLIC_API_URL`: `https://ppa-api-production.up.railway.app`
4. Click **Deploy**. Vercel will automatically build and serve the App Router globally with edge caching.

---

## Option 3: Manual Production Setup on Linux VPS

### Step 1: Install Python 3.12 and Node.js 20+
```bash
sudo apt update && sudo apt install -y python3.12 python3.12-venv nodejs npm
```

### Step 2: Setup Python Virtual Environment & Install Dependencies
```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 3: Run Backend with Systemd or PM2
```bash
# Using PM2 or Uvicorn directly
uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 2
```

### Step 4: Build and Serve Next.js
```bash
cd frontend
npm ci
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run build
npm run start -- -p 3000
```

---

## 🛡️ Production Health & Monitoring

* **Liveness & Readiness Probe**: `GET /api/health`
  Returns HTTP 200 with database connectivity and table counts:
  ```json
  {
    "status": "healthy",
    "database": "connected",
    "table_counts": {
      "market_prices": 744,
      "market_generation": 744,
      "market_forecasts": 744,
      "weather_timeseries": 3720
    }
  }
  ```
* **Auto-Seeding**: If deployed on a blank container without persistent volumes, the backend automatically seeds the database on first boot from bundled Parquet files in `data/parquet/`.
