import os
import sys
import urllib.request
import runpy

RAW_UI_URL = "https://raw.githubusercontent.com/Dawg244/Netra/master/ui.py"
APP_NAME = "NETRA"

def get_cache_dir():
    root = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    path = os.path.join(root, APP_NAME, "github_ui")
    os.makedirs(path, exist_ok=True)
    return path

def download_ui():
    cache = get_cache_dir()
    target = os.path.join(cache, "ui.py")
    request = urllib.request.Request(
        RAW_UI_URL,
        headers={"User-Agent": "NETRA-Launcher"}
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        source = response.read().decode("utf-8")

    marker = 'BASE_DIR = os.path.dirname(os.path.abspath(__file__))'
    if marker in source:
        replacement = """if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_DIR = BASE_DIR
try:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    _netra_test = os.path.join(CONFIG_DIR, ".netra_write_test")
    with open(_netra_test, "a", encoding="utf-8"):
        pass
    os.remove(_netra_test)
except Exception:
    CONFIG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "NETRA")
    os.makedirs(CONFIG_DIR, exist_ok=True)"""
        source = source.replace(marker, replacement, 1)

    with open(target, "w", encoding="utf-8") as f:
        f.write(source)
    return target

def main():
    try:
        ui_path = download_ui()
    except Exception as exc:
        ui_path = os.path.join(get_cache_dir(), "ui.py")
        if not os.path.exists(ui_path):
            raise RuntimeError(
                "NETRA could not download ui.py from GitHub and no cached copy exists.\n"
                f"URL: {RAW_UI_URL}\n\nError: {exc}"
            )

    runpy.run_path(ui_path, run_name="__main__")

if __name__ == "__main__":
    main()
