class RoomManager:
    def __init__(self):
        self.rooms: dict[str, dict] = {}

    def get_or_create(self, room_id: str) -> dict:
        if room_id not in self.rooms:
            self.rooms[room_id] = {
                "meta": {
                    "title": "運動会ポイントボード",
                    "teamAName": "チームA",
                    "teamBName": "チームB",
                },
                "events": {},
                "locks": {},
            }
        return self.rooms[room_id]

    def set_state(self, room_id: str, state: dict):
        self.rooms[room_id] = state