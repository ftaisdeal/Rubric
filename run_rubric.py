"""Entry point for the packaged app (PyInstaller can't run `-m rubric`)."""

from rubric.ui import main

if __name__ == "__main__":
    main()
