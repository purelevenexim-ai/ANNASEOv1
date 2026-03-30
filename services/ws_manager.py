from typing import Dict, List
from fastapi import WebSocket


class WSManager:
    def __init__(self):
        self.connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, project_id: str, websocket: WebSocket):
        await websocket.accept()
        self.connections.setdefault(project_id, []).append(websocket)

    def disconnect(self, project_id: str, websocket: WebSocket):
        room = self.connections.get(project_id)
        if room and websocket in room:
            room.remove(websocket)
            if not room:
                self.connections.pop(project_id, None)

    async def broadcast(self, project_id: str, message: dict):
        for ws in list(self.connections.get(project_id, [])):
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect(project_id, ws)


ws_manager = WSManager()
