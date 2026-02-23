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
- [X] Create spaced repetition algorithm with option for different books to be shown more or less frequently.
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
- [X] Log daily review activity (e.g., number of highlights reviewed, number of highlights discarded with date) and provide a nice heatmap visualization of review activity over time on the dashboard page.
- [X] Create a nice heatmap visualization of number of highlights made over time (using the dates associated to any highlight that has this data) on the dashboard page.

Nice to haves:
- [X] Create Favicon (small icon shown in browser tab) and add to the application.
- [X] Create automatic import of book metadata and book cover image from external sources (e.g., Google Books API, Open Library API) based on book title and author.
- [X] Enhance aestethics (make more visually appealing) of the UI 
    - [X] utilize CSS framework (e.g., Tailwind CSS, Bootstrap) for a minimalistic look with nice fonts and color schemes consistent throughout the application.
    - [X] Remove navigation header from book page (make it full screen) and create a back button to go back to the library (in a similar way as was done for daily higlight page).
    - [X] optional: navigation bar at the left
    - [X] Remove "Discard" and "Restore" buttons and replace with icons only and remove trashcan before "Discarded Highlights" section.
    - [X] Fix dark mode.
    - [X] Always have the navigation header at the top of the page and under it potentially a title (e.g., "Library"), except for daily review page and book view page.
    - [X] Use fonts more appropriate for reading/books (more pleasing and less "computer-like")
        - [X] Use title font for "Daily Review" 
- [X] Investigate the logic and and scripts one by one to see whether there are any optimizations possible to reduce code redundancy and improve efficiency.
- [X] Also show page numbers for favorite and discarded html views.
- [X] Think about how to best order higlights in book view (e.g., by date added, by location in book, by favorite status)
- [X] Daily Review page
    - [X] Add feedback button in between "Discard " and "Done" buttons to allow users to provide feedback on how often they would like to see this higlight. This should link to a variable that gives a weight to the highlight (low or high) that influences how often it is shown in future reviews.
        - [X] Similar to how there is a feedback button of higlight frequency on the daily review cards, with a weight, add a feedback this button on the highlight edit box used for the book detail page, favorite page, and discard page; and show the current weight state too.
    - [X] Add cover image to higlights shown in daily review.
- [X] Book import - The Book title should also be required column and the required boxes should not be red anymore if there is a selection made.
restore highlights
- [X] Download theme, icons and fonts and serve them locally to reduce dependency on external sources.
- [X] Fix dark mode dashboard
    - [ ] heatmaps 
    - [X] colored text of "Discarded" and "Favorites" should be black
- [X] Turn it into a web-app installable through browser (e.g., safari to iPhone or chrome to computer)
- [X] For import allow "Diagnostic mode" to be turned off/on, with a simple switch, speeding up import.
- [X] Make daily review text and icons smaller in general, but also resize if there is a lot of text (also for mobile).
- [X] Make the aestethics of the discarded and favorited pages consistent with the book page: (1) do not show header with links, but instead a back button at top left with text "Dashboard" (2) Use the same font and font size for book titles (and remove the box around it).
- [X] Fix error daily review.
For the daily review cards, sometimes the highlights and/or comments are very long, forcing users to have to scroll. Please dynamically adjust the size of the "highlight and comment text to compensate for this, when reaching the maximum vertical height.
- [X] For the settings page, change the "Daily Review Count" part from a text box into a slider, from 1-15; in this same box also add a Highlight Recency slider with at the left extreme older and at the right newer, for which should also be a variable created for our model that determines which entries are shown on daily review. 
- [X] At the bottom of the setttings tab, add a complete reset of library button to the settings page that resets/deletes the entire database, with a danger field, saying something like that there is no going back and that everything will be permanently deleted. This should
- [X] Add a thunderbolt symbol to the top right of the pages with the navigation header, which should be filled in with gold/orange/yellow (whatever is best) if there is at least a one day streak. And if the streak is multiple days, there should be a number to its right indicating the length of the streak in days.
- [X] Test all functionalities of the recommendation algorithm using diagnostic tests
- [ ] Make sure it works well on mobile devices.
- [ ] Turn this application into a Dockerfile and docker-compose.yml
- [ ] Design a whole suite of tests, to test all important fuctionalities of this web app in a rigorous manner, allowing for automatic checking with a "checkmark"/pass upon success on GitHub.

Upcoming Features:

- [ ] Fix dark mode on the heatmaps displayed on the dashboard page, which currently shows a bright white background not designed with tailwind styling in mind.
- [ ] Enable different kinds of sorting of highlights on the book page, discarded page and favorited pages, including by page number (if these exist), by date of created, data of last modified (e.g., favorited, edited text, etc.)
- [ ] Enable daily email notifications with X number of highlights.
- [ ] Enable more types of import.
- [ ] Utilize more of the horizontal space available for screens with landscape orientation (e.g., monitors, tv's, tablets) for The main pages: dashboard, library, import and settings.