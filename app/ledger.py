"""Two-party, append-only, hash-chained gold ledger.

Every entry starts as a *pending proposal*. It is written to the chain only when
BOTH the jeweller and the karigar have approved it. Each chained entry stores the
SHA-256 hash of the previous entry, so any later edit breaks the chain and is
detected by `verify()`. SQLite triggers additionally block UPDATE/DELETE on the chain.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from datetime import date, datetime

GENESIS_HASH = "0" * 64
PARTIES = ("jeweller", "karigar")


def _canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _ts(at) -> str:
    if at is None:
        return datetime.now().isoformat(timespec="seconds")
    if isinstance(at, (date, datetime)):
        return at.isoformat()
    return str(at)


def entry_hash(seq: int, entry_type: str, payload: dict, approved_at: str, prev_hash: str) -> str:
    body = _canon({"seq": seq, "type": entry_type, "payload": payload, "approved_at": approved_at})
    return hashlib.sha256((prev_hash + body).encode("utf-8")).hexdigest()


class Ledger:
    def __init__(self, path: str = ":memory:"):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS pending (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                proposed_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                jeweller_ok INTEGER NOT NULL DEFAULT 0,
                karigar_ok INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'PENDING',
                note TEXT
            );
            CREATE TABLE IF NOT EXISTS chain (
                seq INTEGER PRIMARY KEY,
                entry_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                approved_at TEXT NOT NULL,
                prev_hash TEXT NOT NULL,
                hash TEXT NOT NULL,
                pending_id INTEGER
            );
            CREATE TRIGGER IF NOT EXISTS chain_no_update BEFORE UPDATE ON chain
                BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END;
            CREATE TRIGGER IF NOT EXISTS chain_no_delete BEFORE DELETE ON chain
                BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END;
            """
        )
        self.conn.commit()

    # ---------------------------------------------------------------- proposals
    def propose(self, entry_type: str, payload: dict, proposed_by: str, at=None) -> int:
        """Create a pending entry. The proposing party (if jeweller/karigar) approves implicitly."""
        with self.lock:
            j_ok = 1 if proposed_by == "jeweller" else 0
            k_ok = 1 if proposed_by == "karigar" else 0
            cur = self.conn.execute(
                "INSERT INTO pending (entry_type, payload, proposed_by, created_at, jeweller_ok, karigar_ok)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (entry_type, _canon(payload), proposed_by, _ts(at), j_ok, k_ok),
            )
            self.conn.commit()
            return cur.lastrowid

    def get_pending(self, pending_id: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM pending WHERE id = ?", (pending_id,)).fetchone()
        return self._pending_row(row) if row else None

    def pending(self, status: str = "PENDING") -> list[dict]:
        rows = self.conn.execute("SELECT * FROM pending WHERE status = ? ORDER BY id", (status,)).fetchall()
        return [self._pending_row(r) for r in rows]

    def approve(self, pending_id: int, party: str, at=None) -> dict | None:
        """Record one party's approval. Returns the chained entry once both have approved."""
        if party not in PARTIES:
            raise ValueError(f"party must be one of {PARTIES}")
        with self.lock:
            p = self.get_pending(pending_id)
            if p is None or p["status"] != "PENDING":
                raise ValueError(f"pending entry {pending_id} is not open")
            col = "jeweller_ok" if party == "jeweller" else "karigar_ok"
            self.conn.execute(f"UPDATE pending SET {col} = 1 WHERE id = ?", (pending_id,))
            p = self.get_pending(pending_id)
            if p["jeweller_ok"] and p["karigar_ok"]:
                entry = self._append(p["entry_type"], p["payload"], at, pending_id)
                self.conn.execute("UPDATE pending SET status = 'LOCKED' WHERE id = ?", (pending_id,))
                self.conn.commit()
                return entry
            self.conn.commit()
            return None

    def reject(self, pending_id: int, party: str, note: str = "") -> None:
        with self.lock:
            self.conn.execute(
                "UPDATE pending SET status = 'REJECTED', note = ? WHERE id = ? AND status = 'PENDING'",
                (f"{party}: {note}".strip(), pending_id),
            )
            self.conn.commit()

    def record_both(self, entry_type: str, payload: dict, at=None) -> dict:
        """Propose and approve by both parties in one step (used when replaying dummy data)."""
        pid = self.propose(entry_type, payload, "jeweller", at)
        return self.approve(pid, "karigar", at)

    # -------------------------------------------------------------------- chain
    def _append(self, entry_type: str, payload: dict, at, pending_id: int | None) -> dict:
        last = self.conn.execute("SELECT seq, hash FROM chain ORDER BY seq DESC LIMIT 1").fetchone()
        seq = (last["seq"] + 1) if last else 1
        prev = last["hash"] if last else GENESIS_HASH
        approved_at = _ts(at)
        h = entry_hash(seq, entry_type, payload, approved_at, prev)
        self.conn.execute(
            "INSERT INTO chain (seq, entry_type, payload, approved_at, prev_hash, hash, pending_id)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (seq, entry_type, _canon(payload), approved_at, prev, h, pending_id),
        )
        return {"seq": seq, "entry_type": entry_type, "payload": payload,
                "approved_at": approved_at, "prev_hash": prev, "hash": h}

    def entries(self) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM chain ORDER BY seq").fetchall()
        return [{"seq": r["seq"], "entry_type": r["entry_type"], "payload": json.loads(r["payload"]),
                 "approved_at": r["approved_at"], "prev_hash": r["prev_hash"], "hash": r["hash"]}
                for r in rows]

    def verify(self) -> dict:
        """Recompute every hash. Returns where the chain first breaks, if anywhere."""
        prev = GENESIS_HASH
        entries = self.entries()
        for e in entries:
            expected = entry_hash(e["seq"], e["entry_type"], e["payload"], e["approved_at"], prev)
            if e["prev_hash"] != prev or e["hash"] != expected:
                return {"ok": False, "length": len(entries), "broken_at": e["seq"]}
            prev = e["hash"]
        return {"ok": True, "length": len(entries), "broken_at": None, "head": prev}

    @staticmethod
    def _pending_row(r) -> dict:
        return {"id": r["id"], "entry_type": r["entry_type"], "payload": json.loads(r["payload"]),
                "proposed_by": r["proposed_by"], "created_at": r["created_at"],
                "jeweller_ok": bool(r["jeweller_ok"]), "karigar_ok": bool(r["karigar_ok"]),
                "status": r["status"], "note": r["note"]}
