# FreeWise

Wisdom should not be locked behind a paywall (if you have the resources to host it yourself). FreeWise is a minimal self-hosted web application--inspired by [Readwise](https://readwise.io/)--for managing and reviewing highlights from books and articles. Built with FastAPI, SQLModel, and HTMX, it provides a simple interface for capturing highlights, organizing them, and scheduling daily reviews using spaced repetition principles.

The web application is still _under development_. If you would like to contribute to this project, please do not hesitate to reach out and/or submit issues and pull requests.

## Quick Start

```bash
docker compose up
```

The application will be available at http://localhost:8000

## Testing and Development

For testing and development, clone the repository and install the required dependencies:

```bash
git clone
cd freewise
pip install -r requirements.txt
```

Run the application using Uvicorn:

```powershell
uvicorn app.main:app --reload
```

The application will be available at http://localhost:8000

## To-Do

- [X] Make sure it works well on mobile devices (e.g., Library page).
- [ ] Create import option from Meebook e-reader.
- [ ] Fix dark mode on the heatmaps displayed on the dashboard page, which currently shows a bright white background not designed with tailwind styling in mind.
- [ ] Turn this application into a Dockerfile and docker-compose.yml
- [ ] Design a whole suite of tests, to test all important fuctionalities of this web app in a rigorous manner, allowing for automatic checking with a "checkmark"/pass upon success on GitHub.

## Upcoming Features/Changes

- [ ] Enable different kinds of sorting of highlights on the book page, discarded page and favorited pages, including by page number (if these exist), by date of created, data of last modified (e.g., favorited, edited text, etc.)
- [ ] Enable daily email notifications with X number of highlights.
- [ ] Enable more types of import.
- [ ] Utilize more of the horizontal space available for screens with landscape orientation (e.g., monitors, tv's, tablets) for The main pages: dashboard, library, import and settings.