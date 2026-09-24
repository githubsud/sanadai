import os

import pytest

os.environ.setdefault("WARM_UP", "false")  # no background model loading during tests

from app.db import repo  # noqa: E402


@pytest.fixture(scope="session")
def db_ready():
    if not repo.db_path().exists():
        pytest.skip("db/sanad.db not built (run scripts/download_data.py && scripts/build_db.py)")
    return True
