# FreeWise

A minimal self-hosted web application for managing and reviewing highlights from books and articles. Built with FastAPI, SQLModel, and HTMX, it provides a simple interface for capturing highlights, organizing them, and scheduling daily reviews using spaced repetition principles.

## Quick Start

```bash
docker compose up
```

The application will be available at http://localhost:8000

## To-Do

- [ ] if there is no date available for import set to null and also don't show them in the book UI
- [ ] improve the UI: 
    - [ ] hearts instead of stars
    - [ ] remove text of symbols (or make it show when hovering on it)
    - [ ] remove book ID