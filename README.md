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

PostgreSQL settings are prepared through environment variables but are not started or connected by this setup. Fleet features, models, authentication, and Celery are intentionally not included yet.
