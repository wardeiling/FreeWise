# FreeWise

[![CI](https://github.com/wardeiling/FreeWise/actions/workflows/ci.yml/badge.svg)](https://github.com/wardeiling/FreeWise/actions/workflows/ci.yml)
![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)
![License: MIT](https://img.shields.io/badge/license-CC0-green)
![Docker](https://img.shields.io/badge/docker-ready-blue?logo=docker)
![PWA](https://img.shields.io/badge/PWA-installable-purple?logo=pwa)

> A minimal, self-hosted web app for managing and reviewing book and article highlights — inspired by [Readwise](https://readwise.io/), without the subscription.

Wisdom should not be locked behind a paywall. FreeWise is built with **FastAPI**, **SQLModel**, **HTMX**, and **TailwindCSS**, and runs entirely in a single Docker container with no external dependencies.

> [!NOTE]
> This project is under active development. Contributions, issues, and pull requests are welcome.

---

## Features

- 📚 **Library** — organise highlights by book or article, with searchable cover images
- 🔁 **Spaced Repetition Review** — daily review sessions driven by a weighted recall algorithm
- ⭐ **Favourites & Discards** — curate your collection by surfacing the best highlights
- 🏷️ **Tags** — tag books for flexible filtering and organisation
- 📥 **Multiple Import Sources** — Readwise CSV, Meebook HTML export, and custom CSV
- 📤 **Export** — export your full library to CSV at any time
- 📊 **Dashboard** — review streak tracker and activity heatmap
- 📱 **Mobile-friendly** — responsive layout that works across phones, tablets, and desktops
- 🔧 **Installable as a PWA** — add FreeWise to your home screen on iOS/Android (Safari → *Share → Add to Home Screen*) or install it as a desktop app via Chrome, Edge, or Brave

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | [FastAPI](https://fastapi.tiangolo.com/) + [SQLModel](https://sqlmodel.tiangolo.com/) |
| Database | SQLite (file-based, zero config) |
| Frontend | [HTMX](https://htmx.org/) + [TailwindCSS](https://tailwindcss.com/) + [Lucide Icons](https://lucide.dev/) |
| Templating | Jinja2 |
| Container | Docker + Docker Compose |

---

## Quick Start

> **Requirements:** [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/) (included in Docker Desktop).

```bash
git clone https://github.com/wardeiling/FreeWise.git
cd FreeWise
docker compose up -d --build
```

Open **http://localhost:8063** in your browser.

The first build takes ~2 minutes (downloads base images and compiles CSS). Subsequent starts are instant.

---

## Docker Reference

### Common commands

| Task | Command |
|---|---|
| Start (first time or after update) | `docker compose up -d --build` |
| Start (no rebuild) | `docker compose up -d` |
| Stop (data preserved) | `docker compose down` |
| Stop and wipe all data | `docker compose down -v` |
| Follow logs | `docker compose logs -f` |
| Restart the container | `docker compose restart freewise` |

### Updating to a newer version

```bash
git pull
docker compose up -d --build
```

### Data persistence

All user data is stored in two named Docker volumes that survive container restarts and image upgrades:

| Volume | Mount path | Contents |
|---|---|---|
| `freewise-db` | `/srv/freewise/db` | SQLite database |
| `freewise-covers` | `/srv/freewise/app/static/uploads/covers` | Uploaded book cover images |

### Backing up your data

```bash
# Database
docker run --rm \
  -v freewise-db:/data \
  -v "$(pwd)":/backup \
  alpine tar czf /backup/freewise-db-backup.tar.gz -C /data .

# Cover images
docker run --rm \
  -v freewise-covers:/data \
  -v "$(pwd)":/backup \
  alpine tar czf /backup/freewise-covers-backup.tar.gz -C /data .
```

### Changing the port

Edit `docker-compose.yml` and change the host-side port:

```yaml
ports:
  - "YOUR_PORT:8063"   # e.g. "80:8063" to serve on standard HTTP
```

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `FREEWISE_DB_URL` | `sqlite:///./db/freewise.db` | SQLAlchemy database URL |

---

## Local Development

Use this setup for contributing to the project or running without Docker.

**Prerequisites:** Python 3.12+, Node.js 20+ (for CSS compilation)

```bash
git clone https://github.com/wardeiling/FreeWise.git
cd FreeWise

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # macOS / Linux
.venv\Scripts\Activate.ps1       # Windows PowerShell

# Install Python dependencies
pip install -r requirements.txt

# Build TailwindCSS (one-time or when templates change)
npm install
npm run build:css

# Start the development server with hot-reload
uvicorn app.main:app --reload
```

The application will be available at **http://localhost:8000**.

---

## Running Tests

The test suite uses `pytest` with `pytest-asyncio` and covers all major application features.

```bash
pytest
```

To run a specific test file:

```bash
pytest tests/test_import_export.py -v
```

<!-- CI runs automatically on every push via [GitHub Actions](.github/workflows/ci.yml). -->

---

## Project Structure

```
app/
├── main.py              # FastAPI application entry point
├── db.py                # Database engine and session helpers
├── models.py            # SQLModel ORM models
├── routers/             # Route handlers (dashboard, library, highlights, …)
├── templates/           # Jinja2 HTML templates
├── static/              # CSS, JS, uploaded covers
└── utils/               # Import parsers (Readwise, Meebook, custom CSV)
tests/                   # pytest test suite
Dockerfile               # Multi-stage production image (Node → Python)
docker-compose.yml       # Single-service deployment with named volumes
```

---

## Contributing

Contributions are very welcome. To get started:

1. Fork the repository and create a feature branch.
2. Make your changes, adding or updating tests as appropriate.
3. Ensure the full test suite passes (`pytest`).
4. Open a pull request with a clear description of the change.

For larger changes or new features, please open an issue first to discuss the approach.

---

## Roadmap

- [ ] Sorting options for highlights (by page number, date created, date last modified)
- [ ] Daily email digest with a configurable number of highlights
- [ ] Additional import sources
- [ ] Improved wide-screen layout for dashboard, library, import, and settings pages

---

## License

This project is licensed under the [MIT License](LICENSE).