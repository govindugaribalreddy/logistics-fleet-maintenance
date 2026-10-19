# logistics-fleet-maintenance

## Day 1 setup

### Backend

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate  # Git Bash on Windows
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

The health endpoint is available at `http://localhost:8000/api/health/`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Set `VITE_API_URL` in a local `.env` file when the API is not at its default URL. Use `.env.example` as a reference; it contains no real credentials.

## Tests and checks

```bash
cd backend && python manage.py check && pytest
cd frontend && npm test && npm run build
```

## PostgreSQL and Docker Compose

The development Compose stack runs PostgreSQL as `db` and Django as `web`. Django connects to PostgreSQL using the Compose service name `db`; database data is persisted in the `postgres_data` volume.

Create a local `.env` from `.env.example` and replace the placeholder secret/password values if desired:

```bash
cp .env.example .env
```

Start the database and Django service:

```bash
docker compose up --build
```

The Django container waits for PostgreSQL to become healthy, runs migrations, and serves the API at `http://localhost:8000`. To initialize or rerun migrations manually:

```bash
docker compose run --rm web python manage.py migrate
```

Run backend checks and tests in the Compose Django environment:

```bash
docker compose run --rm web python manage.py check
docker compose run --rm web pytest
```

Stop the services while preserving the database volume:

```bash
docker compose down
```

To remove the persisted development database as well:

```bash
docker compose down -v
```

Redis, RabbitMQ, Celery, Prometheus, and Grafana are intentionally not included yet. Fleet features, database models, and authentication are also not included.
