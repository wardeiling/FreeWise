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

Core functionality:
- [X] if there is no date available for import (e.g., empty entry) set to null and also don't show them in the book UI
- [X] Remove date book added column from the library (and everywhere else in GUI)
    - [X] GUI library
    - [X] library.py
- [X] improve the UI: 
    - [X] remove text of symbols (or make it show when hovering on it)
    - [X] remove book ID
- [X] Improve daily review page: show at the centered top of the page that this is the "Daily Review" (full screen, so no header; only at the left top a back icon to return to dashboard) and then have the box of that particular note with at the bottom in the box a favorite and edit button. Then outside the highlight box have one X button (with circle around it) saying under it in small font "Discard" and then right of it a green checkmark button (with circle around it) with in small font under it "Done". When pressing either Discard or done, it moves a new higlight into view after which the same process follows, until all X (default is 5) higlights are completed.
- [X] Add deduplication for import
- [ ] Create spaced repetition algorithm with option for different books to be shown more or less frequently.
- [X] Evaluate whether there is any added benefit to changing export format (if not change back to readwise and simplify import)
    - [X] Remove columns from export and import: higlight_id, book_id, last_reviewed_at, created_at, updated_at, book_created_at, book_updated_at
        - [X] From import
        - [X] From export: also make higlighted_at date format consistent with readwise format
- [X] Added button to delete book from library.
- [X] prevents discarded entries to be favorited and edited; and favorite entries to be discarded
- [X] Import
    - [X] Identify issue with skipped lines with readwise import.
    - [X] Define a separate function for readwise import and book import.
    - [X] For book import, allow for import with book section information and page numbers.
    - [X] Correctly import book sections from readwise (readwise exports it to the higlight column with the comment .h1 for heading 1, .h2 for heading 2, etc.)
- [X] Add progress bar for imports (of large files)
- [X] Allow users to edit book information (e.g., author name, title) after import.
- [X] If there are no higlights in the library, change dashboard header to "No highlights available. Please import some highlights to get started." And if there are less then the amount of set daily reviews, change to "Only X highlights available. Please import more highlights to get the full experience."
- [X] Show discarded higlights for each book in a dedicated section at the bottom of the book page and make sure higlights are automatically moved from and to there.
- [X] Remove discarded text from entries (highlights) in discarded section (redundant).
- [ ] Log daily review activity (e.g., number of highlights reviewed, number of highlights discarded with date) and provide a nice heatmap visualization of review activity over time on the dashboard page.
- [ ] Create a nice heatmap visualization of number of highlights made over time on the dashboard page.

Nice to haves:
- [ ] Create Favicon (small icon shown in browser tab) and add to the application.
- [ ] Create automatic import of book metadata and book cover image from external sources (e.g., Google Books API, Open Library API) based on book title and author.
- [X] Enhance aestethics (make more visually appealing) of the UI 
    - [X] utilize CSS framework (e.g., Tailwind CSS, Bootstrap) for a minimalistic look with nice fonts and color schemes consistent throughout the application.
    - [X] Remove navigation header from book page (make it full screen) and create a back button to go back to the library (in a similar way as was done for daily higlight page).
    - [X] optional: navigation bar at the left
    - [X] Remove "Discard" and "Restore" buttons and replace with icons only and remove trashcan before "Discarded Highlights" section.
    - [X] Fix dark mode.
    - [X] Always have the navigation header at the top of the page and under it potentially a title (e.g., "Library"), except for daily review page and book view page.
    - [X] Use fonts more appropriate for reading/books (more pleasing and less "computer-like")
        - [X] Use title font for "Daily Review" 
- [ ] Investigate the logic and and scripts one by one to see whether there are any optimizations possible to reduce code redundancy and improve efficiency.
- [X] Also show page numbers for favorite and discarded html views.
- [ ] Think about how to best order higlights in book view (e.g., by date added, by location in book, by favorite status)
- [ ] Sort higlights in favorite and discarded by the date they were favorited/discarded (more recent up top)
- [ ] Daily Review page
    - [ ] Add feedback button in between "Discard " and "Done" buttons to allow users to provide feedback on how often they would like to see this higlight.
    - [ ] Add book title, author and cover image to higlights shown in daily review.
- [ ] Book import - The Book title should also be required column and the required boxes should not be red anymore if there is a selection made.

vertical line yellow
fix disc. favs.
testore high.
Black tiles dashboard