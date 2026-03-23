import os
import tempfile

import pytest

# Override DATA_DIR before importing database to use a temp directory
_tmp = tempfile.mkdtemp()
os.environ.setdefault("DATA_DIR", _tmp)
os.environ.setdefault("BOOKS_DIR", os.path.join(_tmp, "books"))
os.environ.setdefault("LOGS_DIR", os.path.join(_tmp, "logs"))


@pytest.fixture()
def tmp_db(tmp_path):
    """Provide a fresh database in a temporary directory for each test."""
    from src import config
    from src import database as db

    original_path = config.DB_PATH
    db_module_path = db.DB_PATH

    test_db = str(tmp_path / "test.db")
    config.DB_PATH = test_db
    db.DB_PATH = test_db

    # Close any existing per-thread connection so init_database uses the new path
    db.close_connections()

    db.init_database()

    yield test_db

    # Close per-thread connection before restoring paths
    db.close_connections()

    config.DB_PATH = original_path
    db.DB_PATH = db_module_path
