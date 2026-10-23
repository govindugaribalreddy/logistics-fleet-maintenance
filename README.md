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

Redis, RabbitMQ, Celery, Prometheus, and Grafana are intentionally not included yet. Automated fleet scheduling is also not included.

## Authentication and roles

All API endpoints require an authenticated Django user. The API accepts Django Session authentication and HTTP Basic authentication. Roles are represented by Django Groups with these exact names:

- `Fleet Manager`: full vehicle and service-record management access.
- `Technician`: read access to fleet reference data and access only to service records assigned to the technician whose email matches the user email. Technicians may create their own service records.
- `Read-only Viewer`: read-only access to API data.

Create an administrator interactively; Django prompts for the username and password so no credentials are stored in source code:

```bash
docker compose run --rm web python manage.py createsuperuser
```

After signing in to Django admin, create the three Groups above and assign users to the appropriate group. For local development without Docker, run the same command from `backend/` inside the activated virtual environment. Authentication is intentionally limited to Django-supported mechanisms for now; token/JWT authentication can be added later without changing the role model.
