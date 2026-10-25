"""
WebSocket 连接管理器
支持多客户端连接、广播推送、断线处理
"""

from fastapi import WebSocket
from typing import List
import json


class WebSocketManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"[WS] Client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        print(f"[WS] Client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, data: dict):
        """向所有连接的客户端广播数据"""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(data)
            except Exception:
                disconnected.append(connection)

        for conn in disconnected:
            self.disconnect(conn)

    async def send_to(self, websocket: WebSocket, data: dict):
        """向指定客户端发送数据"""
        try:
            await websocket.send_json(data)
        except Exception:
            self.disconnect(websocket)
