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

- [X] if there is no date available for import (e.g., empty entry) set to null and also don't show them in the book UI
- [X] Remove date book added column from the library (and everywhere else in GUI)
    - [X] GUI library
    - [X] library.py
- [ ] improve the UI: 
    - [ ] remove text of symbols (or make it show when hovering on it)
    - [X] remove book ID
    - [ ] Search for templates online and make it more visually appealing (maybe navigation bar at the left?); and add consistent styling (e.g., Tailwind).
- [ ] Improve daily review page: show at the top of the page that this is the "Daily Review" and then have the box of that particular note with at the bottom in the box a favorite and edit button. Then outside the highlight box have one X button saying under it in small font "Discard" and then right of it a checkmark button with in small font under it "Done". When pressing either Discard or done, it moves a new higlight into view after which the same process follows, until all X (default is 5) higlights are completed.
- [X] Add deduplication for import
- [ ] Create spaced repetition algorithm with option for different books to be shown more or less frequently.
- [X] Evaluate whether there is any added benefit to changing export format (if not change back to readwise and simplify import)
    - [X] Remove columns from export and import: higlight_id, book_id, last_reviewed_at, created_at, updated_at, book_created_at, book_updated_at
        - [X] From import
        - [X] From export: also make higlighted_at date format consistent with readwise format
- [ ] Improve location of import/export functionality.
- [X] Added button to delete book from library.
- [X] prevents discarded entries to be favorited and edited; and favorite entries to be discarded
- [ ] Import
    - [ ] Define a separate function for readwise import and book import
    - [ ] For book import, allow for import with book section information and page numbers (annoyingly ReadWise does not provide this for export of csv)
    - [ ] Make sure that variables not used are still saved at import (e.g., color, location (order of note in book), location type) and also appropriately exported.
- [X] Add progress bar for imports (of large files)
- [X] Allow users to edit book information (e.g., author name, title) after import.
- [ ] If there are no higlights in the library, change dashboard header to "No highlights available. Please import some highlights to get started." And if there are less then the amount of set daily reviews, change to "Only X highlights available. Please import more highlights to get the full experience."
- [ ] Show discarded higlights for each book at the bottom of the book page.