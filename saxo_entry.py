"""PyInstaller entry point for the standalone Saxo CLI."""

from cli.saxocli import main

if __name__ == "__main__":
    raise SystemExit(main())
