import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Computer Use GUI")
    parser.add_argument("--lang", choices=("ko", "en"), default="ko")
    args = parser.parse_args()

    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("PySide6 not installed. pip install -e '.[gui]'")
        return 1

    from computer_use.gui.main_window import MainWindow

    if MainWindow is None:
        print("GUI unavailable")
        return 1

    app = QApplication(sys.argv)
    window = MainWindow(lang=args.lang)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
