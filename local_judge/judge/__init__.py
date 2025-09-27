__all__ = ["MainWindow"]

# Lazy import to avoid requiring PySide6 when using non-GUI modules
def __getattr__(name):
    if name == "MainWindow":
        from .main_window import MainWindow  # type: ignore
        return MainWindow
    raise AttributeError(name)

