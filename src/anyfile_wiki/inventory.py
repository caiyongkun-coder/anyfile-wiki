from __future__ import annotations

from pathlib import Path
import json
import sqlite3
from typing import Iterable

from .parse import ExtractResult
from .scan import ScanEntry


SCHEMA_VERSION = 2


class Inventory:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "Inventory":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _init_schema(self) -> None:
        self.connection.executescript(
            """
            PRAGMA journal_mode = WAL;

            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS files (
                path TEXT PRIMARY KEY,
                normalized_path TEXT NOT NULL,
                name TEXT NOT NULL,
                extension TEXT NOT NULL,
                is_dir INTEGER NOT NULL,
                exists_now INTEGER NOT NULL,
                size_bytes INTEGER,
                mtime REAL,
                ctime REAL,
                access_policy TEXT NOT NULL,
                policy_source TEXT NOT NULL,
                policy_reason TEXT NOT NULL,
                is_excluded INTEGER NOT NULL,
                is_read_allowed INTEGER NOT NULL,
                is_extract_allowed INTEGER NOT NULL,
                is_index_allowed INTEGER NOT NULL,
                is_embedding_allowed INTEGER NOT NULL,
                metadata_only INTEGER NOT NULL,
                last_seen_at TEXT NOT NULL,
                extra_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS extractions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT NOT NULL,
                parser TEXT NOT NULL,
                status TEXT NOT NULL,
                output_path TEXT,
                error TEXT,
                embedding_allowed INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                source_size_bytes INTEGER,
                source_mtime REAL,
                output_sha256 TEXT,
                skip_reason TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_extractions_path ON extractions(path);
            CREATE INDEX IF NOT EXISTS idx_extractions_status ON extractions(status);
            CREATE INDEX IF NOT EXISTS idx_extractions_parser ON extractions(parser);
            """
        )
        self._ensure_extraction_columns()
        self.connection.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
            ("schema_version", str(SCHEMA_VERSION)),
        )
        self.connection.commit()

    def upsert_entries(self, entries: Iterable[ScanEntry]) -> int:
        count = 0
        with self.connection:
            for entry in entries:
                decision = entry.decision
                self.connection.execute(
                    """
                    INSERT OR REPLACE INTO files (
                        path, normalized_path, name, extension, is_dir, exists_now,
                        size_bytes, mtime, ctime,
                        access_policy, policy_source, policy_reason,
                        is_excluded, is_read_allowed, is_extract_allowed,
                        is_index_allowed, is_embedding_allowed, metadata_only,
                        last_seen_at, extra_json
                    ) VALUES (
                        :path, :normalized_path, :name, :extension, :is_dir, :exists_now,
                        :size_bytes, :mtime, :ctime,
                        :access_policy, :policy_source, :policy_reason,
                        :is_excluded, :is_read_allowed, :is_extract_allowed,
                        :is_index_allowed, :is_embedding_allowed, :metadata_only,
                        :last_seen_at, :extra_json
                    )
                    """,
                    {
                        "path": entry.path,
                        "normalized_path": decision.path,
                        "name": entry.name,
                        "extension": entry.extension,
                        "is_dir": int(entry.is_dir),
                        "exists_now": int(entry.exists_now),
                        "size_bytes": entry.size_bytes,
                        "mtime": entry.mtime,
                        "ctime": entry.ctime,
                        "access_policy": decision.access_policy,
                        "policy_source": decision.policy_source,
                        "policy_reason": decision.reason,
                        "is_excluded": int(decision.is_excluded),
                        "is_read_allowed": int(decision.is_read_allowed),
                        "is_extract_allowed": int(decision.is_extract_allowed),
                        "is_index_allowed": int(decision.is_index_allowed),
                        "is_embedding_allowed": int(decision.is_embedding_allowed),
                        "metadata_only": int(decision.metadata_only),
                        "last_seen_at": entry.last_seen_at,
                        "extra_json": json.dumps(entry.extra, ensure_ascii=False, sort_keys=True),
                    },
                )
                count += 1
        return count

    def mark_missing_under_roots(
        self,
        roots: Iterable[str | Path],
        seen_paths: Iterable[str | Path],
    ) -> int:
        root_keys = [_path_order_key(root).rstrip("/") for root in roots]
        root_keys = [key for key in root_keys if key]
        seen_keys = {_path_order_key(path) for path in seen_paths}
        if not root_keys:
            return 0

        rows = self.connection.execute(
            """
            SELECT path, normalized_path
            FROM files
            WHERE exists_now = 1
            """
        ).fetchall()
        missing_paths = [
            str(row["path"])
            for row in rows
            if _under_any_root(str(row["normalized_path"]), root_keys)
            and str(row["normalized_path"]).casefold() not in seen_keys
        ]
        if not missing_paths:
            return 0

        with self.connection:
            self.connection.executemany(
                "UPDATE files SET exists_now = 0 WHERE path = ?",
                [(path,) for path in missing_paths],
            )
        return len(missing_paths)

    def stats(self) -> dict[str, int]:
        rows = self.connection.execute(
            """
            SELECT access_policy, COUNT(*) AS count
            FROM files
            WHERE exists_now = 1
            GROUP BY access_policy
            """
        ).fetchall()
        return {str(row["access_policy"]): int(row["count"]) for row in rows}

    def list_files(
        self,
        *,
        limit: int = 50,
        access_policy: str | None = None,
        include_dirs: bool = True,
    ) -> list[dict]:
        where = ["exists_now = 1"]
        params: dict[str, object] = {"limit": limit}
        if access_policy:
            where.append("access_policy = :access_policy")
            params["access_policy"] = access_policy
        if not include_dirs:
            where.append("is_dir = 0")
        sql = f"""
            SELECT *
            FROM files
            WHERE {' AND '.join(where)}
            ORDER BY last_seen_at DESC, path ASC
            LIMIT :limit
        """
        rows = self.connection.execute(sql, params).fetchall()
        return [_row_to_dict(row) for row in rows]

    def list_files_after(
        self,
        *,
        after_path: str | Path | None = None,
        limit: int = 50,
        access_policy: str | None = None,
        include_dirs: bool = True,
    ) -> list[dict]:
        where = ["exists_now = 1"]
        params: dict[str, object] = {"limit": limit}
        if after_path:
            where.append("lower(normalized_path) > :after_path")
            params["after_path"] = _path_order_key(after_path)
        if access_policy:
            where.append("access_policy = :access_policy")
            params["access_policy"] = access_policy
        if not include_dirs:
            where.append("is_dir = 0")
        sql = f"""
            SELECT *
            FROM files
            WHERE {' AND '.join(where)}
            ORDER BY lower(normalized_path) ASC, path ASC
            LIMIT :limit
        """
        rows = self.connection.execute(sql, params).fetchall()
        return [_row_to_dict(row) for row in rows]

    def get_file(self, path: str | Path) -> dict | None:
        candidate = str(path)
        normalized = str(Path(path)).replace("\\", "/")
        row = self.connection.execute(
            """
            SELECT *
            FROM files
            WHERE path = ? OR normalized_path = ? OR normalized_path = ?
            LIMIT 1
            """,
            (candidate, candidate.replace("\\", "/"), normalized),
        ).fetchone()
        return _row_to_dict(row) if row else None

    def source_stats(self, *, limit: int = 20) -> list[tuple[str, int]]:
        rows = self.connection.execute(
            """
            SELECT policy_source, COUNT(*) AS count
            FROM files
            WHERE exists_now = 1
            GROUP BY policy_source
            ORDER BY count DESC, policy_source ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [(str(row["policy_source"]), int(row["count"])) for row in rows]

    def add_extract_results(self, results: Iterable[ExtractResult]) -> int:
        count = 0
        with self.connection:
            for result in results:
                self.connection.execute(
                    """
                    INSERT INTO extractions (
                        path, parser, status, output_path, error,
                        embedding_allowed, created_at,
                        source_size_bytes, source_mtime, output_sha256, skip_reason
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        result.path,
                        result.parser,
                        result.status,
                        result.output_path,
                        result.error,
                        int(result.embedding_allowed),
                        result.created_at,
                        result.source_size_bytes,
                        result.source_mtime,
                        result.output_sha256,
                        result.skip_reason,
                    ),
                )
                count += 1
        return count

    def extract_stats(self) -> dict[str, int]:
        rows = self.connection.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM extractions
            GROUP BY status
            ORDER BY status ASC
            """
        ).fetchall()
        return {str(row["status"]): int(row["count"]) for row in rows}

    def list_extracts(
        self,
        *,
        limit: int = 50,
        status: str | None = None,
        parser: str | None = None,
        path: str | Path | None = None,
    ) -> list[dict]:
        where: list[str] = []
        params: dict[str, object] = {"limit": limit}
        if status:
            where.append("status = :status")
            params["status"] = status
        if parser:
            where.append("parser = :parser")
            params["parser"] = parser
        if path:
            where.append("path = :path")
            params["path"] = str(path)
        sql = """
            SELECT *
            FROM extractions
        """
        if where:
            sql += f" WHERE {' AND '.join(where)}"
        sql += " ORDER BY created_at DESC, id DESC LIMIT :limit"
        rows = self.connection.execute(sql, params).fetchall()
        return [_extract_row_to_dict(row) for row in rows]

    def latest_extracts_by_path(self) -> dict[str, dict]:
        rows = self.connection.execute(
            """
            SELECT e.*
            FROM extractions e
            JOIN (
                SELECT path, MAX(id) AS max_id
                FROM extractions
                GROUP BY path
            ) latest ON latest.max_id = e.id
            """
        ).fetchall()
        return {str(row["path"]): _extract_row_to_dict(row) for row in rows}

    def latest_success_by_path(self) -> dict[str, dict]:
        rows = self.connection.execute(
            """
            SELECT e.*
            FROM extractions e
            JOIN (
                SELECT path, MAX(id) AS max_id
                FROM extractions
                WHERE status = 'ok'
                GROUP BY path
            ) latest ON latest.max_id = e.id
            """
        ).fetchall()
        return {str(row["path"]): _extract_row_to_dict(row) for row in rows}

    def latest_analyzable_extracts_by_path(self) -> dict[str, dict]:
        rows = self.connection.execute(
            """
            SELECT e.*,
                   f.access_policy AS access_policy,
                   f.policy_source AS policy_source,
                   f.policy_reason AS policy_reason,
                   f.is_read_allowed AS is_read_allowed,
                   f.is_extract_allowed AS is_extract_allowed,
                   f.is_index_allowed AS is_index_allowed,
                   f.is_embedding_allowed AS is_embedding_allowed
            FROM extractions e
            JOIN (
                SELECT path, MAX(id) AS max_id
                FROM extractions
                WHERE status IN ('ok', 'up_to_date')
                  AND output_path IS NOT NULL
                GROUP BY path
            ) latest ON latest.max_id = e.id
            LEFT JOIN files f ON f.path = e.path
            """
        ).fetchall()
        return {str(row["path"]): _extract_row_to_dict(row) for row in rows}

    def _ensure_extraction_columns(self) -> None:
        rows = self.connection.execute("PRAGMA table_info(extractions)").fetchall()
        columns = {str(row["name"]) for row in rows}
        required = {
            "source_size_bytes": "INTEGER",
            "source_mtime": "REAL",
            "output_sha256": "TEXT",
            "skip_reason": "TEXT",
        }
        for name, definition in required.items():
            if name not in columns:
                self.connection.execute(f"ALTER TABLE extractions ADD COLUMN {name} {definition}")
        self.connection.commit()


def _row_to_dict(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["is_dir"] = bool(data["is_dir"])
    data["exists_now"] = bool(data["exists_now"])
    data["is_excluded"] = bool(data["is_excluded"])
    data["is_read_allowed"] = bool(data["is_read_allowed"])
    data["is_extract_allowed"] = bool(data["is_extract_allowed"])
    data["is_index_allowed"] = bool(data["is_index_allowed"])
    data["is_embedding_allowed"] = bool(data["is_embedding_allowed"])
    data["metadata_only"] = bool(data["metadata_only"])
    data["extra"] = json.loads(data.pop("extra_json") or "{}")
    return data


def _extract_row_to_dict(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["embedding_allowed"] = bool(data["embedding_allowed"])
    for key in ("is_read_allowed", "is_extract_allowed", "is_index_allowed", "is_embedding_allowed"):
        if key in data and data[key] is not None:
            data[key] = bool(data[key])
    return data


def _path_order_key(path: str | Path) -> str:
    return str(Path(path).absolute()).replace("\\", "/").casefold()


def _under_any_root(path: str, root_keys: list[str]) -> bool:
    normalized = path.replace("\\", "/").casefold().rstrip("/")
    return any(normalized == root or normalized.startswith(root + "/") for root in root_keys)
