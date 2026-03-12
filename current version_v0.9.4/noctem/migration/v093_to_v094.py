"""One-time data migration utility: v0.9.3 snapshot -> v0.9.4 object core."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import noctem.db as db_module


TABLE_COPY_ORDER = [
    "goals",
    "projects",
    "tasks",
    "time_blocks",
    "conversations",
    "voice_journals",
    "sources",
    "knowledge_chunks",
]

TABLE_CLEAR_ORDER = list(reversed(TABLE_COPY_ORDER))

OBJECT_MAPPINGS = [
    ("goal", "goals", "id"),
    ("project", "projects", "id"),
    ("task", "tasks", "id"),
    ("time_block", "time_blocks", "id"),
    ("conversation", "conversations", "id"),
    ("voice_journal", "voice_journals", "id"),
    ("source", "sources", "id"),
    ("knowledge_chunk", "knowledge_chunks", "id"),
]


@dataclass
class MigrationPaths:
    source_db: Path
    target_db: Path
    export_dir: Path
    source_data_dir: Path
    target_data_dir: Path


def _utc_now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def default_source_db() -> Path:
    return _repo_root() / "historical-versions" / "0.9.3" / "noctem" / "data" / "noctem.db"


def default_target_db() -> Path:
    env_data_dir = Path(os.environ["NOCTEM_DATA_DIR"]) if os.environ.get("NOCTEM_DATA_DIR") else None
    if env_data_dir is not None:
        return env_data_dir / "noctem.db"
    return _repo_root() / "current version_v0.9.4" / "noctem" / "data" / "noctem.db"


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()]


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key in row.keys():
        value = row[key]
        if isinstance(value, bytes):
            payload[key] = value.decode("utf-8", errors="replace")
        else:
            payload[key] = value
    return payload


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def _safe_json_loads(payload: str | None, fallback: Any) -> Any:
    if not payload:
        return fallback
    try:
        return json.loads(payload)
    except Exception:
        return fallback


def _init_target_schema(target_db: Path) -> None:
    target_db.parent.mkdir(parents=True, exist_ok=True)
    if target_db.exists():
        conn = sqlite3.connect(str(target_db))
        try:
            table_row = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'time_blocks'"
            ).fetchone()
            if table_row:
                cols = {
                    row[1]
                    for row in conn.execute('PRAGMA table_info("time_blocks")').fetchall()
                }
                if "external_event_id" not in cols:
                    conn.execute("ALTER TABLE time_blocks ADD COLUMN external_event_id TEXT")
                if "all_day" not in cols:
                    conn.execute("ALTER TABLE time_blocks ADD COLUMN all_day INTEGER DEFAULT 0")
                cols = {
                    row[1]
                    for row in conn.execute('PRAGMA table_info("time_blocks")').fetchall()
                }
                if "gcal_event_id" in cols and "external_event_id" in cols:
                    conn.execute(
                        """
                        UPDATE time_blocks
                        SET external_event_id = COALESCE(external_event_id, gcal_event_id)
                        WHERE gcal_event_id IS NOT NULL
                        """
                    )
                conn.commit()
        finally:
            conn.close()
    original_path = db_module.DB_PATH
    try:
        db_module.DB_PATH = target_db
        db_module.init_db()
    finally:
        db_module.DB_PATH = original_path


def _extract_seed_snapshot(source_conn: sqlite3.Connection) -> dict[str, Any]:
    goals = []
    if _table_exists(source_conn, "goals"):
        for row in source_conn.execute(
            "SELECT id, name, type, description FROM goals ORDER BY id ASC"
        ).fetchall():
            goals.append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "type": row["type"],
                    "description": row["description"],
                }
            )

    projects = []
    if _table_exists(source_conn, "projects"):
        for row in source_conn.execute(
            """
            SELECT p.id, p.name, p.status, p.summary, g.name AS goal_name
            FROM projects p
            LEFT JOIN goals g ON g.id = p.goal_id
            ORDER BY p.id ASC
            """
        ).fetchall():
            entry = {
                "id": row["id"],
                "name": row["name"],
                "status": row["status"],
                "summary": row["summary"],
            }
            if row["goal_name"]:
                entry["goal"] = row["goal_name"]
            projects.append(entry)

    tasks = []
    if _table_exists(source_conn, "tasks"):
        for row in source_conn.execute(
            """
            SELECT t.*, p.name AS project_name
            FROM tasks t
            LEFT JOIN projects p ON p.id = t.project_id
            ORDER BY t.id ASC
            """
        ).fetchall():
            entry = {
                "id": row["id"],
                "name": row["name"],
                "status": row["status"],
                "importance": row["importance"],
                "due_date": row["due_date"],
                "due_time": row["due_time"],
                "recurrence_rule": row["recurrence_rule"],
            }
            if row["project_name"]:
                entry["project"] = row["project_name"]
            tags = _safe_json_loads(row["tags"], None)
            if tags:
                entry["tags"] = tags
            tasks.append(entry)

    calendar_urls = []
    if _table_exists(source_conn, "config"):
        row = source_conn.execute(
            "SELECT value FROM config WHERE key = 'ics_urls'"
        ).fetchone()
        if row:
            loaded = _safe_json_loads(row["value"], [])
            if isinstance(loaded, list):
                calendar_urls = loaded

    return {
        "_noctem_seed_version": "1.0",
        "_exported_at": _utc_now_iso(),
        "goals": goals,
        "projects": projects,
        "tasks": tasks,
        "calendar_urls": calendar_urls,
    }


def _dump_table_rows(source_conn: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    if not _table_exists(source_conn, table):
        return []
    rows = source_conn.execute(f'SELECT * FROM "{table}" ORDER BY id ASC').fetchall()
    return [_row_to_dict(row) for row in rows]


def _copy_table_rows(
    source_conn: sqlite3.Connection,
    target_conn: sqlite3.Connection,
    table: str,
) -> dict[str, Any]:
    if not _table_exists(source_conn, table):
        return {"table": table, "copied_rows": 0, "source_exists": False}
    if not _table_exists(target_conn, table):
        return {"table": table, "copied_rows": 0, "source_exists": True, "target_exists": False}

    source_cols = _table_columns(source_conn, table)
    target_cols = _table_columns(target_conn, table)
    common_cols = [col for col in source_cols if col in target_cols]
    if not common_cols:
        return {"table": table, "copied_rows": 0, "source_exists": True, "target_exists": True}

    select_sql = f'SELECT {", ".join(common_cols)} FROM "{table}"'
    rows = source_conn.execute(select_sql).fetchall()
    target_conn.execute(f'DELETE FROM "{table}"')
    if rows:
        placeholders = ", ".join("?" for _ in common_cols)
        insert_sql = (
            f'INSERT OR REPLACE INTO "{table}" ({", ".join(common_cols)}) '
            f"VALUES ({placeholders})"
        )
        target_conn.executemany(insert_sql, [tuple(row[col] for col in common_cols) for row in rows])
    return {
        "table": table,
        "copied_rows": len(rows),
        "columns": common_cols,
        "source_exists": True,
        "target_exists": True,
    }


def _copy_ics_urls_config(source_conn: sqlite3.Connection, target_conn: sqlite3.Connection) -> dict[str, Any]:
    if not _table_exists(source_conn, "config") or not _table_exists(target_conn, "config"):
        return {"copied": False}
    row = source_conn.execute("SELECT value FROM config WHERE key = 'ics_urls'").fetchone()
    if row is None:
        return {"copied": False}
    target_conn.execute(
        "INSERT OR REPLACE INTO config (key, value) VALUES ('ics_urls', ?)",
        (row["value"],),
    )
    return {"copied": True}


def _object_id(object_type: str, typed_id: int) -> str:
    return f"{object_type}:{typed_id}"


def _populate_object_core(
    target_conn: sqlite3.Connection,
    *,
    run_id: str,
) -> dict[str, Any]:
    now_iso = _utc_now_iso()
    for table in ("object_context_docs", "object_refs", "object_versions", "object_events", "objects"):
        if _table_exists(target_conn, table):
            target_conn.execute(f'DELETE FROM "{table}"')

    counts: dict[str, int] = {}
    event_total = 0
    version_total = 0
    for object_type, table, id_col in OBJECT_MAPPINGS:
        if not _table_exists(target_conn, table):
            continue
        rows = target_conn.execute(f'SELECT * FROM "{table}" ORDER BY "{id_col}" ASC').fetchall()
        object_count = 0
        for row in rows:
            typed_id_raw = row[id_col]
            if typed_id_raw is None:
                continue
            typed_id = int(typed_id_raw)
            object_count += 1

            snapshot = _row_to_dict(row)
            created_at = snapshot.get("created_at") or now_iso
            updated_at = snapshot.get("updated_at") or created_at
            object_id = _object_id(object_type, typed_id)
            event_id = f"mig-{run_id}-{object_type}-{typed_id}"
            version_id = f"ov-mig-{run_id}-{object_type}-{typed_id}-1"
            metadata = {
                "migration": {
                    "from_version": "0.9.3",
                    "to_version": "0.9.4",
                    "run_id": run_id,
                    "source_table": table,
                },
                "provenance": {
                    "original_created_at": snapshot.get("created_at"),
                },
            }
            target_conn.execute(
                """
                INSERT OR REPLACE INTO objects
                (object_id, object_type, typed_id, review_state, metadata_json, created_at, updated_at)
                VALUES (?, ?, ?, 'active', ?, ?, ?)
                """,
                (object_id, object_type, typed_id, json.dumps(metadata, ensure_ascii=False), created_at, updated_at),
            )
            target_conn.execute(
                """
                INSERT OR REPLACE INTO object_events
                (event_id, operation, summary, details_json, undo_actions_json, correlation_id, created_at)
                VALUES (?, 'migration.import', ?, ?, '[]', ?, ?)
                """,
                (
                    event_id,
                    f"Migrated {object_type}:{typed_id} from v0.9.3",
                    json.dumps(
                        {
                            "run_id": run_id,
                            "source_table": table,
                            "typed_id": typed_id,
                        },
                        ensure_ascii=False,
                    ),
                    f"migration:{run_id}",
                    created_at,
                ),
            )
            target_conn.execute(
                """
                INSERT OR REPLACE INTO object_versions
                (version_id, object_id, version_num, snapshot_json, parent_version_id, event_id, created_by, created_at)
                VALUES (?, ?, 1, ?, NULL, ?, ?, ?)
                """,
                (
                    version_id,
                    object_id,
                    json.dumps(snapshot, ensure_ascii=False, default=str),
                    event_id,
                    f"migration:{run_id}",
                    created_at,
                ),
            )
            target_conn.execute(
                """
                INSERT OR REPLACE INTO object_refs (object_id, head_version_id, updated_at)
                VALUES (?, ?, ?)
                """,
                (object_id, version_id, updated_at),
            )
            event_total += 1
            version_total += 1
        counts[object_type] = object_count
    return {
        "object_counts_by_type": counts,
        "object_total": sum(counts.values()),
        "event_total": event_total,
        "version_total": version_total,
    }


def _count_rows(conn: sqlite3.Connection, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return int(conn.execute(f'SELECT COUNT(1) FROM "{table}"').fetchone()[0])


def _verify_integrity(
    source_conn: sqlite3.Connection,
    target_conn: sqlite3.Connection,
) -> dict[str, Any]:
    table_counts: dict[str, dict[str, Any]] = {}
    ok = True
    for table in TABLE_COPY_ORDER:
        source_count = _count_rows(source_conn, table)
        target_count = _count_rows(target_conn, table)
        matched = source_count == target_count
        if not matched:
            ok = False
        table_counts[table] = {
            "source_count": source_count,
            "target_count": target_count,
            "matched": matched,
        }

    expected_objects = sum(_count_rows(target_conn, mapping[1]) for mapping in OBJECT_MAPPINGS)
    object_count = _count_rows(target_conn, "objects")
    version_count = _count_rows(target_conn, "object_versions")
    ref_count = _count_rows(target_conn, "object_refs")
    event_count = _count_rows(target_conn, "object_events")
    object_match = object_count == expected_objects
    if not object_match:
        ok = False

    broken_refs = 0
    object_missing_refs = 0
    missing_parents = 0
    if _table_exists(target_conn, "object_refs") and _table_exists(target_conn, "object_versions"):
        broken_refs = int(
            target_conn.execute(
                """
                SELECT COUNT(1)
                FROM object_refs r
                LEFT JOIN object_versions v ON v.version_id = r.head_version_id
                WHERE r.head_version_id IS NOT NULL AND v.version_id IS NULL
                """
            ).fetchone()[0]
        )
    if _table_exists(target_conn, "objects") and _table_exists(target_conn, "object_refs"):
        object_missing_refs = int(
            target_conn.execute(
                """
                SELECT COUNT(1)
                FROM objects o
                LEFT JOIN object_refs r ON r.object_id = o.object_id
                WHERE r.object_id IS NULL
                """
            ).fetchone()[0]
        )
    if _table_exists(target_conn, "object_versions"):
        missing_parents = int(
            target_conn.execute(
                """
                SELECT COUNT(1)
                FROM object_versions v
                LEFT JOIN object_versions p ON p.version_id = v.parent_version_id
                WHERE v.parent_version_id IS NOT NULL AND p.version_id IS NULL
                """
            ).fetchone()[0]
        )
    if broken_refs or object_missing_refs or missing_parents:
        ok = False

    wiki_checks: list[dict[str, Any]] = []
    if _table_exists(source_conn, "knowledge_chunks") and _table_exists(target_conn, "knowledge_chunks"):
        sample_queries = ["task", "project", "calendar", "meeting"]
        for query in sample_queries:
            pattern = f"%{query.lower()}%"
            source_rows = source_conn.execute(
                """
                SELECT chunk_id
                FROM knowledge_chunks
                WHERE lower(content) LIKE ?
                ORDER BY chunk_id ASC
                LIMIT 20
                """,
                (pattern,),
            ).fetchall()
            target_rows = target_conn.execute(
                """
                SELECT chunk_id
                FROM knowledge_chunks
                WHERE lower(content) LIKE ?
                ORDER BY chunk_id ASC
                LIMIT 20
                """,
                (pattern,),
            ).fetchall()
            source_set = {row["chunk_id"] for row in source_rows}
            target_set = {row["chunk_id"] for row in target_rows}
            matched = source_set == target_set
            wiki_checks.append(
                {
                    "query": query,
                    "source_hits": len(source_set),
                    "target_hits": len(target_set),
                    "matched": matched,
                }
            )
            if not matched:
                ok = False

    return {
        "ok": ok,
        "table_counts": table_counts,
        "object_core": {
            "expected_objects": expected_objects,
            "object_count": object_count,
            "version_count": version_count,
            "ref_count": ref_count,
            "event_count": event_count,
            "object_count_matched": object_match,
            "broken_head_refs": broken_refs,
            "objects_missing_refs": object_missing_refs,
            "versions_missing_parents": missing_parents,
        },
        "wiki_checks": wiki_checks,
    }


def _copy_wiki_artifacts(source_data_dir: Path, target_data_dir: Path) -> dict[str, Any]:
    copied: dict[str, Any] = {"copied_dirs": [], "missing_dirs": [], "skipped_same_path": []}
    for dirname in ("sources", "chroma"):
        source_dir = source_data_dir / dirname
        target_dir = target_data_dir / dirname
        if not source_dir.exists():
            copied["missing_dirs"].append(str(source_dir))
            continue
        if source_dir.resolve() == target_dir.resolve():
            copied["skipped_same_path"].append(str(source_dir))
            continue
        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.copytree(source_dir, target_dir)
        copied["copied_dirs"].append(str(target_dir))
    return copied


def _build_paths(
    *,
    source_db: Path | None,
    target_db: Path | None,
    export_dir: Path | None,
) -> MigrationPaths:
    resolved_source = (source_db or default_source_db()).expanduser().resolve()
    resolved_target = (target_db or default_target_db()).expanduser().resolve()
    if resolved_source == resolved_target:
        raise ValueError("Source and target databases must be different files")
    if not resolved_source.exists():
        raise FileNotFoundError(f"Source database not found: {resolved_source}")
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    resolved_export = (
        export_dir.expanduser().resolve()
        if export_dir is not None
        else (resolved_target.parent / "migration_exports" / f"v093_to_v094_{timestamp}")
    )
    return MigrationPaths(
        source_db=resolved_source,
        target_db=resolved_target,
        export_dir=resolved_export,
        source_data_dir=resolved_source.parent,
        target_data_dir=resolved_target.parent,
    )


def run_v093_to_v094_migration(
    *,
    source_db: Path | None = None,
    target_db: Path | None = None,
    export_dir: Path | None = None,
    copy_wiki_artifacts: bool = True,
) -> dict[str, Any]:
    paths = _build_paths(source_db=source_db, target_db=target_db, export_dir=export_dir)
    paths.export_dir.mkdir(parents=True, exist_ok=True)
    run_id = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    started_at = _utc_now_iso()

    backup_path = None
    if paths.target_db.exists():
        backup_path = paths.target_db.with_name(
            f"{paths.target_db.stem}.backup_before_v094_migration_{run_id}{paths.target_db.suffix}"
        )
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(paths.target_db, backup_path)

    _init_target_schema(paths.target_db)

    source_conn = _connect(paths.source_db)
    target_conn = _connect(paths.target_db)
    table_copy_results: list[dict[str, Any]] = []
    object_result: dict[str, Any] = {}
    verification: dict[str, Any] = {}
    wiki_copy_result: dict[str, Any] = {"copied_dirs": [], "missing_dirs": []}
    copied_ics_urls = {"copied": False}

    try:
        seed_snapshot = _extract_seed_snapshot(source_conn)
        _write_json(paths.export_dir / "seed_snapshot.json", seed_snapshot)
        _write_json(paths.export_dir / "conversations_rows.json", _dump_table_rows(source_conn, "conversations"))
        _write_json(paths.export_dir / "voice_journals_rows.json", _dump_table_rows(source_conn, "voice_journals"))
        _write_json(paths.export_dir / "time_blocks_rows.json", _dump_table_rows(source_conn, "time_blocks"))

        target_conn.execute("PRAGMA foreign_keys = OFF")
        for table in TABLE_CLEAR_ORDER:
            if _table_exists(target_conn, table):
                target_conn.execute(f'DELETE FROM "{table}"')
        for table in TABLE_COPY_ORDER:
            table_copy_results.append(_copy_table_rows(source_conn, target_conn, table))
        copied_ics_urls = _copy_ics_urls_config(source_conn, target_conn)
        target_conn.execute("PRAGMA foreign_keys = ON")

        object_result = _populate_object_core(target_conn, run_id=run_id)
        target_conn.commit()

        if copy_wiki_artifacts:
            wiki_copy_result = _copy_wiki_artifacts(paths.source_data_dir, paths.target_data_dir)

        verification = _verify_integrity(source_conn, target_conn)
    finally:
        source_conn.close()
        target_conn.close()

    finished_at = _utc_now_iso()
    report = {
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "source_db": str(paths.source_db),
        "target_db": str(paths.target_db),
        "target_backup_db": str(backup_path) if backup_path else None,
        "export_dir": str(paths.export_dir),
        "seed_snapshot_file": str(paths.export_dir / "seed_snapshot.json"),
        "table_copy_results": table_copy_results,
        "copied_ics_urls": copied_ics_urls,
        "object_import": object_result,
        "wiki_copy": wiki_copy_result,
        "verification": verification,
    }
    _write_json(paths.export_dir / "migration_report.json", report)
    return report


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run v0.9.3 -> v0.9.4 Noctem data migration")
    parser.add_argument("--source-db", type=Path, default=None, help="Path to source v0.9.3 sqlite database")
    parser.add_argument("--target-db", type=Path, default=None, help="Path to target v0.9.4 sqlite database")
    parser.add_argument("--export-dir", type=Path, default=None, help="Directory for snapshot exports and migration report")
    parser.add_argument(
        "--skip-wiki-copy",
        action="store_true",
        help="Skip copying source/chroma directories from source data dir",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    report = run_v093_to_v094_migration(
        source_db=args.source_db,
        target_db=args.target_db,
        export_dir=args.export_dir,
        copy_wiki_artifacts=not args.skip_wiki_copy,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if not report.get("verification", {}).get("ok", False):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
