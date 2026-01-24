import os
import re
import subprocess
import sys
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FONT_DIR = os.path.join(ROOT, "app", "static", "fonts")
CSS_DIR = os.path.join(ROOT, "app", "static", "css")
TOOLS_DIR = os.path.join(ROOT, "tools")
TAILWIND_EXE = os.path.join(TOOLS_DIR, "tailwindcss.exe")

FONT_CSS_URLS = [
    "https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700&display=swap",
    "https://fonts.googleapis.com/css2?family=Crimson+Pro:wght@400;600&display=swap",
    "https://fonts.googleapis.com/css2?family=Libre+Baskerville:wght@400;700&display=swap",
]

TAILWIND_URL = "https://github.com/tailwindlabs/tailwindcss/releases/download/v3.4.10/tailwindcss-windows-x64.exe"


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as resp:
        return resp.read()


def ensure_dirs():
    os.makedirs(FONT_DIR, exist_ok=True)
    os.makedirs(CSS_DIR, exist_ok=True)
    os.makedirs(TOOLS_DIR, exist_ok=True)


def download_fonts():
    print("Downloading Google Fonts CSS...")
    css = ""
    for url in FONT_CSS_URLS:
        css += fetch(url).decode("utf-8") + "\n"

    font_urls = re.findall(r"url\((https://fonts\.gstatic\.com/s/[^)]+)\)", css)
    downloaded = {}

    print(f"Found {len(font_urls)} font files...")
    for url in font_urls:
        if url in downloaded:
            continue
        filename = os.path.basename(url)
        font_path = os.path.join(FONT_DIR, filename)
        if not os.path.exists(font_path):
            data = fetch(url)
            with open(font_path, "wb") as f:
                f.write(data)
        downloaded[url] = filename

    for url, filename in downloaded.items():
        css = css.replace(url, f"/static/fonts/{filename}")

    fonts_css_path = os.path.join(CSS_DIR, "fonts.css")
    with open(fonts_css_path, "w", encoding="utf-8") as f:
        f.write(css)

    print(f"Wrote {fonts_css_path}")


def download_tailwind():
    if os.path.exists(TAILWIND_EXE):
        print("Tailwind binary already present.")
        return

    print("Downloading Tailwind standalone binary...")
    data = fetch(TAILWIND_URL)
    with open(TAILWIND_EXE, "wb") as f:
        f.write(data)
    print(f"Saved {TAILWIND_EXE}")


def build_tailwind():
    input_css = os.path.join(ROOT, "app", "static", "css", "input.css")
    output_css = os.path.join(ROOT, "app", "static", "css", "tailwind.css")
    config = os.path.join(ROOT, "tailwind.config.js")

    if not os.path.exists(TAILWIND_EXE):
        raise RuntimeError("Tailwind binary missing.")

    print("Building Tailwind CSS...")
    result = subprocess.run(
        [TAILWIND_EXE, "-c", config, "-i", input_css, "-o", output_css, "--minify"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        raise RuntimeError("Tailwind build failed")

    print(f"Built {output_css}")


def main():
    ensure_dirs()
    download_fonts()
    download_tailwind()
    build_tailwind()
    print("Done.")


if __name__ == "__main__":
    main()
