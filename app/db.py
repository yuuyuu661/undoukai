import os
import json
import asyncpg
from dotenv import load_dotenv
await conn.execute("SET TIME ZONE 'Asia/Tokyo'")

load_dotenv()


class Database:
    def __init__(self):
        self.pool: asyncpg.Pool | None = None
        self.db_url = os.getenv("DATABASE_URL")

        if not self.db_url:
            raise ValueError("DATABASE_URL が設定されていません")

    async def connect(self):
        self.pool = await asyncpg.create_pool(self.db_url)

        async with self.pool.acquire() as conn:
            await conn.execute("SET TIME ZONE 'Asia/Tokyo'")

    async def close(self):
        if self.pool:
            await self.pool.close()

    async def init_db(self):
        async with self.pool.acquire() as conn:

            await conn.execute("""
            CREATE TABLE IF NOT EXISTS scoreboard_meta (
                room_id TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT '運動会ポイントボード',
                team_a_name TEXT NOT NULL DEFAULT 'チームA',
                team_b_name TEXT NOT NULL DEFAULT 'チームB',
                updated_at TIMESTAMP DEFAULT NOW()
            )
            """)

            await conn.execute("""
            CREATE TABLE IF NOT EXISTS scoreboard_events (
                room_id TEXT NOT NULL,
                event_id TEXT NOT NULL,
                payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                locked BOOLEAN NOT NULL DEFAULT FALSE,
                updated_at TIMESTAMP DEFAULT NOW(),
                PRIMARY KEY (room_id, event_id)
            )
            """)

            await conn.execute("""
            CREATE TABLE IF NOT EXISTS scoreboard_logs (
                id BIGSERIAL PRIMARY KEY,
                room_id TEXT NOT NULL,
                event_id TEXT,
                editor TEXT,
                action TEXT NOT NULL,
                before_data JSONB,
                after_data JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            )
            """)

    # ===============================
    # 初期ロード（超重要）
    # ===============================
    async def load_room_state(self, room_id: str) -> dict:
        async with self.pool.acquire() as conn:

            meta_row = await conn.fetchrow("""
                SELECT title, team_a_name, team_b_name
                FROM scoreboard_meta
                WHERE room_id = $1
            """, room_id)

            if not meta_row:
                await conn.execute("""
                    INSERT INTO scoreboard_meta (room_id)
                    VALUES ($1)
                    ON CONFLICT DO NOTHING
                """, room_id)

                meta = {
                    "title": "運動会ポイントボード",
                    "teamAName": "チームA",
                    "teamBName": "チームB",
                }
            else:
                meta = {
                    "title": meta_row["title"],
                    "teamAName": meta_row["team_a_name"],
                    "teamBName": meta_row["team_b_name"],
                }

            rows = await conn.fetch("""
                SELECT event_id, payload, locked
                FROM scoreboard_events
                WHERE room_id = $1
            """, room_id)

            events = {}
            locks = {}

            for row in rows:
                events[row["event_id"]] = (
                    json.loads(row["payload"]) if row["payload"] else {}
                )
                locks[row["event_id"]] = row["locked"]

            return {
                "meta": meta,
                "events": events,
                "locks": locks,
            }

    # ===============================
    # META
    # ===============================
    async def save_meta(self, room_id: str, meta: dict, editor: str):

        async with self.pool.acquire() as conn:

            before = await conn.fetchrow("""
                SELECT title, team_a_name, team_b_name
                FROM scoreboard_meta
                WHERE room_id=$1
            """, room_id)

            await conn.execute("""
            INSERT INTO scoreboard_meta(room_id,title,team_a_name,team_b_name,updated_at)
            VALUES($1,$2,$3,$4,NOW())
            ON CONFLICT(room_id)
            DO UPDATE SET
                title=EXCLUDED.title,
                team_a_name=EXCLUDED.team_a_name,
                team_b_name=EXCLUDED.team_b_name,
                updated_at=NOW()
            """, room_id, meta["title"], meta["teamAName"], meta["teamBName"])

            await conn.execute("""
            INSERT INTO scoreboard_logs(room_id,editor,action,before_data,after_data)
            VALUES($1,$2,'update_meta',$3,$4)
            """, room_id, editor,
                json.dumps(dict(before)) if before else None,
                json.dumps(meta)
            )

    # ===============================
    # EVENT保存（リアルタイム用）
    # ===============================
    async def save_event(self, room_id: str, event_id: str, payload: dict, editor: str):

        async with self.pool.acquire() as conn:

            before = await conn.fetchrow("""
                SELECT payload FROM scoreboard_events
                WHERE room_id=$1 AND event_id=$2
            """, room_id, event_id)

            before_json = before["payload"] if before else None
            payload_json = json.dumps(payload)

            await conn.execute("""
            INSERT INTO scoreboard_events(room_id,event_id,payload,updated_at)
            VALUES($1,$2,$3,NOW())
            ON CONFLICT(room_id,event_id)
            DO UPDATE SET payload=$3, updated_at=NOW()
            """, room_id, event_id, payload_json)

            await conn.execute("""
            INSERT INTO scoreboard_logs(room_id,event_id,editor,action,before_data,after_data)
            VALUES($1,$2,$3,'update_event',$4,$5)
            """, room_id, event_id, editor,
                before_json,
                payload_json
            )

    # ===============================
    # LOCK
    # ===============================
    async def set_event_lock(self, room_id: str, event_id: str, locked: bool, editor: str):
        async with self.pool.acquire() as conn:
            await conn.execute("""
            INSERT INTO scoreboard_events(room_id, event_id, locked, updated_at)
            VALUES($1, $2, $3, NOW())
            ON CONFLICT(room_id, event_id)
            DO UPDATE SET locked = $3, updated_at = NOW()
            """, room_id, event_id, locked)

            await conn.execute("""
            INSERT INTO scoreboard_logs(room_id, event_id, editor, action, after_data)
            VALUES($1, $2, $3, 'lock_event', $4)
            """, room_id, event_id, editor, json.dumps({"locked": locked}))

    # ===============================
    # RESET
    # ===============================
    async def reset_room(self, room_id: str, editor: str):

        async with self.pool.acquire() as conn:

            await conn.execute("DELETE FROM scoreboard_events WHERE room_id=$1", room_id)

            await conn.execute("""
            UPDATE scoreboard_meta
            SET title='運動会ポイントボード',
                team_a_name='チームA',
                team_b_name='チームB',
                updated_at=NOW()
            WHERE room_id=$1
            """, room_id)

            await conn.execute("""
            INSERT INTO scoreboard_logs(room_id,editor,action)
            VALUES($1,$2,'reset_room')
            """, room_id, editor)

    # ===============================
    # LOG
    # ===============================
    async def load_logs(self, room_id: str, limit: int = 100):

        async with self.pool.acquire() as conn:

            rows = await conn.fetch("""
            SELECT *
            FROM scoreboard_logs
            WHERE room_id=$1
            ORDER BY created_at DESC
            LIMIT $2
            """, room_id, limit)

            return [dict(r) for r in rows]








