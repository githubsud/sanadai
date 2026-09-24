import pytest

from app.db import repo


@pytest.fixture(scope="session")
def db_ready():
    if not repo.db_path().exists():
        pytest.skip("db/sanad.db not built (run scripts/download_data.py && scripts/build_db.py)")
    return True
