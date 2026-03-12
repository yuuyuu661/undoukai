from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import socketio
import db
import uvicorn

sio = socketio.AsyncServer(cors_allowed_origins="*", async_mode="asgi")
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

socket_app = socketio.ASGIApp(sio, other_asgi_app=app)

@app.on_event("startup")
async def startup():
    await db.init_db()

@app.get("/api/meta/{room}")
async def get_meta(room: str):
    return await db.get_meta(room)

@app.post("/api/meta/{room}")
async def save_meta(room: str, data: dict):
    await db.save_meta(room, data)
    await sio.emit("meta:update", data, room=room)
    return {"ok": True}

@app.get("/api/events/{room}")
async def get_events(room: str):
    return await db.get_events(room)

@app.post("/api/event/{room}/{event_id}")
async def save_event(room: str, event_id: str, data: dict):
    await db.save_event(room, event_id, data)
    await sio.emit("event:update", {"id": event_id, "data": data}, room=room)
    return {"ok": True}

@app.post("/api/lock/{event_id}")
async def lock_event(event_id: str):
    await db.lock_event(event_id)
    await sio.emit("event:lock", event_id)
    return {"ok": True}

@app.get("/api/logs/{room}")
async def logs(room: str):
    return await db.get_logs(room)

@sio.event
async def connect(sid, environ):
    print("connected", sid)

@sio.event
async def join(sid, room):
    sio.enter_room(sid, room)
    print("join", room)

@sio.event
async def disconnect(sid):
    print("disconnect", sid)

if __name__ == "__main__":
    uvicorn.run(socket_app, host="0.0.0.0", port=8000)