from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_check_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_static_css_is_served():
    response = client.get("/static/app.css")
    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]


def test_startup_adds_completion_note_column_to_existing_tasks_table(tmp_path):
    # Deviation from the originally-specified test mechanics: reloading
    # app.db/app.models/app.main mid-suite (importlib.reload) mutates shared
    # module state — a freshly reloaded `Base` starts with empty metadata
    # (app.models must also be reloaded to re-register tables on it), and
    # reloading app.models replaces the Task/Label/... classes with new
    # objects. Because other already-imported test modules do
    # `from app.models import Task` *inside* their test functions (evaluated
    # at run time, not at collection time), they pick up whatever class
    # objects are current in sys.modules when they run. That caused real
    # failures in test_labels.py and test_tasks.py when this test ran first
    # in the suite (SQLAlchemy ObjectDeletedError / identity-map mismatches).
    #
    # Instead, we exercise the exact migration logic added to
    # app.main.on_startup by calling it directly, as a standalone function,
    # against a real sqlite file with a pre-existing (Slice-1-shaped) tasks
    # table missing completion_note. This is a genuine regression test for
    # "start against an old database, don't crash, column gets added" without
    # touching any global module state.
    from sqlalchemy import create_engine, text as sa_text

    from app.main import ensure_completion_note_column

    db_path = tmp_path / "old_schema.db"
    old_engine = create_engine(f"sqlite:///{db_path}")
    with old_engine.connect() as conn:
        conn.execute(sa_text(
            "CREATE TABLE tasks (id INTEGER PRIMARY KEY, workspace_id INTEGER, "
            "owner_id INTEGER, title TEXT, description TEXT, status TEXT, "
            "due_date DATETIME, recurrence_series_id INTEGER, recurrence_pattern TEXT, "
            "recurrence_interval INTEGER, recurrence_days_of_week TEXT, "
            "recurrence_active BOOLEAN, created_at DATETIME, completed_at DATETIME)"
        ))
        conn.commit()

    # Simulates what app.main's startup handler does for a pre-existing
    # Slice 1 database: should not crash, and should add the column.
    ensure_completion_note_column(old_engine)

    with old_engine.connect() as conn:
        columns = {row[1] for row in conn.execute(sa_text("PRAGMA table_info(tasks)"))}
    assert "completion_note" in columns

    # Idempotent: running it again against an already-migrated db is a no-op,
    # not a crash (e.g. from re-adding a duplicate column).
    ensure_completion_note_column(old_engine)

    old_engine.dispose()


def test_startup_adds_redesign_columns_to_existing_tables(tmp_path):
    # Same rationale as test_startup_adds_completion_note_column_to_existing_tasks_table:
    # exercise the migration function directly against a raw-DDL legacy
    # database rather than reloading app modules mid-suite.
    from sqlalchemy import create_engine, text as sa_text

    from app.main import ensure_redesign_columns

    db_path = tmp_path / "pre_redesign.db"
    old_engine = create_engine(f"sqlite:///{db_path}")
    with old_engine.connect() as conn:
        conn.execute(sa_text(
            "CREATE TABLE tasks (id INTEGER PRIMARY KEY, workspace_id INTEGER, "
            "owner_id INTEGER, title TEXT, description TEXT, status TEXT, "
            "due_date DATETIME, recurrence_series_id INTEGER, recurrence_pattern TEXT, "
            "recurrence_interval INTEGER, recurrence_days_of_week TEXT, "
            "recurrence_active BOOLEAN, created_at DATETIME, completed_at DATETIME, "
            "completion_note TEXT)"
        ))
        conn.execute(sa_text(
            "CREATE TABLE requirements (id INTEGER PRIMARY KEY, workspace_id INTEGER, "
            "owner_id INTEGER, title TEXT, description TEXT, business_need TEXT, "
            "acceptance_criteria TEXT, status TEXT, created_at DATETIME)"
        ))
        conn.execute(sa_text(
            "INSERT INTO requirements (id, workspace_id, owner_id, title, description, "
            "business_need, acceptance_criteria, status, created_at) VALUES "
            "(1, 1, 1, 'Legacy req', '', '', '', 'draft', '2026-01-01 00:00:00')"
        ))
        conn.commit()

    ensure_redesign_columns(old_engine)

    with old_engine.connect() as conn:
        task_columns = {row[1] for row in conn.execute(sa_text("PRAGMA table_info(tasks)"))}
        assert "blocked" in task_columns

        requirement_columns = {
            row[1] for row in conn.execute(sa_text("PRAGMA table_info(requirements)"))
        }
        assert "updated_at" in requirement_columns

        backfilled = conn.execute(
            sa_text("SELECT updated_at FROM requirements WHERE id = 1")
        ).scalar()
        assert backfilled == "2026-01-01 00:00:00"

    # Idempotent: running again against an already-migrated db is a no-op.
    ensure_redesign_columns(old_engine)


def test_ensure_completion_note_column_skips_non_sqlite_dialects(monkeypatch):
    from sqlalchemy import create_engine

    from app.main import ensure_completion_note_column

    engine = create_engine("sqlite:///:memory:")
    monkeypatch.setattr(engine.dialect, "name", "postgresql")

    connected = {"value": False}
    original_connect = engine.connect

    def spy_connect(*args, **kwargs):
        connected["value"] = True
        return original_connect(*args, **kwargs)

    monkeypatch.setattr(engine, "connect", spy_connect)

    ensure_completion_note_column(engine)

    assert connected["value"] is False


def test_ensure_redesign_columns_skips_non_sqlite_dialects(monkeypatch):
    from sqlalchemy import create_engine

    from app.main import ensure_redesign_columns

    engine = create_engine("sqlite:///:memory:")
    monkeypatch.setattr(engine.dialect, "name", "postgresql")

    connected = {"value": False}
    original_connect = engine.connect

    def spy_connect(*args, **kwargs):
        connected["value"] = True
        return original_connect(*args, **kwargs)

    monkeypatch.setattr(engine, "connect", spy_connect)

    ensure_redesign_columns(engine)

    assert connected["value"] is False
