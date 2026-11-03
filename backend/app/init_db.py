"""Initialize first schema before starting local workers. Not a migration tool."""
from .main import create_app
if __name__=='__main__':
    app=create_app();app.state.engine.dispose()
