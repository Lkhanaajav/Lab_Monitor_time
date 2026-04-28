"""OU Lab Access Portal — entry point."""
import bootstrap
from ui import theme
from ui.app_shell import AppShell


def main() -> None:
    bootstrap.run()
    theme.apply_theme()
    app = AppShell()
    app.mainloop()


if __name__ == "__main__":
    main()
