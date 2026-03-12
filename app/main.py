from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import socketio
import uvicorn
from db import Database

db = Database()

sio = socketio.AsyncServer(cors_allowed_origins="*", async_mode="asgi")
app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

socket_app = socketio.ASGIApp(sio, other_asgi_app=app)


# ===============================
# 起動
# ===============================
@app.on_event("startup")
async def startup():
    await db.connect()
    await db.init_db()
    print("DB ready")


# ===============================
# 初期ロード
# ===============================
@app.get("/api/state/{room}")
async def load_state(room: str):
    return await db.load_room_state(room)


# ===============================
# META
# ===============================
@app.post("/api/meta/{room}")
async def save_meta(room: str, data: dict):
    editor = data.get("editor", "unknown")
    await db.save_meta(room, data, editor)
    await sio.emit("meta:update", data, room=room)
    return {"ok": True}


# ===============================
# EVENT
# ===============================
@app.post("/api/event/{room}/{event_id}")
async def save_event(room: str, event_id: str, data: dict):
    editor = data.get("editor", "unknown")
    await db.save_event(room, event_id, data, editor)

    await sio.emit(
        "event:update",
        {"event_id": event_id, "data": data},
        room=room
    )
    return {"ok": True}


# ===============================
# LOCK
# ===============================
@app.post("/api/lock/{room}/{event_id}")
async def lock_event(room: str, event_id: str, data: dict):
    editor = data.get("editor", "unknown")
    locked = data.get("locked", True)

    await db.set_event_lock(room, event_id, locked, editor)

    await sio.emit(
        "event:lock",
        {"event_id": event_id, "locked": locked},
        room=room
    )
    return {"ok": True}


# ===============================
# RESET
# ===============================
@app.post("/api/reset/{room}")
async def reset_room(room: str, data: dict):
    editor = data.get("editor", "unknown")

    await db.reset_room(room, editor)

    state = await db.load_room_state(room)

    await sio.emit("state:reset", state, room=room)
    return {"ok": True}


# ===============================
# LOG
# ===============================
@app.get("/api/logs/{room}")
async def get_logs(room: str):
    return await db.load_logs(room)


# ===============================
# SOCKET
# ===============================
@sio.event
async def connect(sid, environ):
    print("connect", sid)


@sio.event
async def join(sid, room):
    sio.enter_room(sid, room)
    print("join", room)

    # join時に初期状態送信
    state = await db.load_room_state(room)
    await sio.emit("state:init", state, to=sid)


@sio.event
async def disconnect(sid):
    print("disconnect", sid)


# ===============================
# RUN
# ===============================
if __name__ == "__main__":
    uvicorn.run(socket_app, host="0.0.0.0", port=8000)
