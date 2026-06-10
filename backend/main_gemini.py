try:
    from .app.main import app
except ImportError:
    from app.main import app
