# FreeWise

Becoming wise should not be locked behind a paywall (if you have the resources to host it yourself). FreeWise is a minimal self-hosted web application--inspired by [Readwise](https://readwise.io/)--for managing and reviewing highlights from books and articles. Built with FastAPI, SQLModel, and HTMX, it provides a simple interface for capturing highlights, organizing them, and scheduling daily reviews using spaced repetition principles.

## Quick Start

```bash
docker compose up
```

The application will be available at http://localhost:8000

## To-Do

- [ ] if there is no date available for import set to null and also don't show them in the book UI
- [ ] improve the UI: 
    - [ ] remove text of symbols (or make it show when hovering on it)
    - [ ] remove book ID
    - [ ] Search for templates online and make it more visually appealing (maybe navigation bar at the left?); and add consistent styling (e.g., Tailwind).
- [ ] Improve daily review page: show at the top of the page that this is the "Daily Review" and then have the box of that particular note with at the bottom in the box a favorite and edit button. Then outside the highlight box have one X button saying under it in small font "Discard" and then right of it a checkmark button with in small font under it "Done". When pressing either Discard or done, it moves a new higlight into view after which the same process follows, until all X (default is 5) higlights are completed.
- [ ] Add deduplication for import
- [ ] Create spaced repetition algorithm with option for different books to be shown more or less frequently.
- [ ] Evaluate whether there is any added benefit to changing export format (if not change back to readwise and simplify import)