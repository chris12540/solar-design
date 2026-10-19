import importlib
import os
from urllib.parse import urlsplit, urlunsplit
import pytest
import psycopg

@pytest.fixture(scope='session')
def test_db_url():
    source=os.environ.get('DATABASE_URL')
    if not source:
        pytest.skip('DATABASE_URL is required for PostgreSQL integration tests')
    u=urlsplit(source)
    maintenance=urlunsplit((u.scheme,u.netloc,'/postgres','',''))
    dbname='solar_designer_test'
    try:
        with psycopg.connect(maintenance, autocommit=True) as c:
            c.execute(f'CREATE DATABASE {dbname}')
    except psycopg.errors.DuplicateDatabase:
        pass
    yield urlunsplit((u.scheme,u.netloc,'/'+dbname,'',''))

@pytest.fixture(scope='session')
def appmod(test_db_url):
    os.environ.update(DATABASE_URL=test_db_url, STAFF_TOKEN='test-staff-token',
        SESSION_SECRET='test-session-secret-with-sufficient-entropy',
        ALLOWED_ORIGINS='http://testserver')
    import backend.app as mod
    importlib.reload(mod)
    mod.init_db()
    yield mod

@pytest.fixture(autouse=True)
def clear_db(request):
    # Keep pure unit tests independent of PostgreSQL. Existing integration tests
    # that request appmod still receive a clean database before each case.
    if 'appmod' not in request.fixturenames:
        return
    appmod=request.getfixturevalue('appmod')
    with appmod.connect() as c:
        c.execute('TRUNCATE runs, rejected_rows, parcels, datasets, county_subdivisions CASCADE')

@pytest.fixture
def client(appmod):
    from fastapi.testclient import TestClient
    with TestClient(appmod.app) as c:
        yield c
