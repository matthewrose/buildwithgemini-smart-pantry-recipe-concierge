"""FastAPI proxy for Smart Pantry & Recipe Concierge (Agent Runtime A2A agent).

The browser talks ONLY to this proxy (same origin, no CORS, no GCP creds in the
browser). The proxy authenticates with Application Default Credentials and
forwards chat to the deployed agent over the A2A protocol, returning replies as
structured parts the chat UI knows how to show:

  * {"kind": "text", "text": ...}  -> a normal chat bubble
  * {"kind": "a2ui", "data": ...}  -> one A2UI message (beginRendering /
    surfaceUpdate); static/index.html renders these as a card.
"""

import os
import uuid

import google.auth
import google.auth.transport.requests
import httpx
from a2a.client import ClientConfig, ClientFactory
from a2a.types import (
    AgentCard,
    FilePart,
    Message,
    Part,
    Role,
    TaskArtifactUpdateEvent,
    TaskQueryParams,
    TextPart,
    TransportProtocol,
)
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

RESOURCE = os.environ.get(
    "AGENT_ENGINE_RESOURCE_NAME",
    "projects/135622055779/locations/us-east1/reasoningEngines/4121585307416002560",
)
AGENT_DIRECTORY = os.environ.get("AGENT_DIRECTORY", "app")
LOCATION = RESOURCE.split("/locations/")[1].split("/")[0]

A2A_BASE = (
    f"https://{LOCATION}-aiplatform.googleapis.com/reasoningEngines/v1/"
    f"{RESOURCE}/api/a2a/{AGENT_DIRECTORY}"
)
A2A_CARD_URL = f"{A2A_BASE}/.well-known/agent-card.json"

_A2UI_MIME = "application/json+a2ui"

_creds, _ = google.auth.default(
    scopes=["https://www.googleapis.com/auth/cloud-platform"]
)


def _auth_headers() -> dict[str, str]:
    _creds.refresh(google.auth.transport.requests.Request())
    return {
        "Authorization": f"Bearer {_creds.token}",
        "Content-Type": "application/json",
    }


app = FastAPI(title="Smart Pantry & Recipe Concierge Proxy")


@app.exception_handler(Exception)
async def _json_errors(request: Request, exc: Exception):
    return JSONResponse(
        status_code=200,
        content={
            "parts": [{"kind": "text", "text": f"Error: {type(exc).__name__}: {exc}"}]
        },
    )


_contexts: dict[str, str] = {}
_card: AgentCard | None = None


async def _get_card(client: httpx.AsyncClient) -> AgentCard:
    global _card
    if _card is None:
        resp = await client.get(A2A_CARD_URL)
        resp.raise_for_status()
        card = AgentCard(**resp.json())
        card.url = A2A_BASE
        _card = card
    return _card


def _extract_parts(parts: list) -> list[dict]:
    out: list[dict] = []
    for p in parts:
        if isinstance(p, str) and p.strip():
            out.append({"kind": "text", "text": p})
            continue
        root = getattr(p, "root", p)
        text_val = getattr(root, "text", None) or (root.get("text") if isinstance(root, dict) else None)
        if text_val:
            out.append({"kind": "text", "text": str(text_val)})
            continue
        data_val = getattr(root, "data", None) or (root.get("data") if isinstance(root, dict) else None)
        if data_val is not None:
            meta = getattr(root, "metadata", None) or (root.get("metadata") if isinstance(root, dict) else {})
            mime = meta.get("mimeType") if isinstance(meta, dict) else getattr(meta, "mimeType", None)
            if mime == _A2UI_MIME:
                out.append({"kind": "a2ui", "data": data_val})
            elif isinstance(data_val, dict) and ("beginRendering" in data_val or "surfaceUpdate" in data_val):
                out.append({"kind": "a2ui", "data": data_val})
            elif isinstance(data_val, str):
                out.append({"kind": "text", "text": data_val})
            continue
        if isinstance(root, FilePart):
            uri = getattr(getattr(root, "file", None), "uri", None)
            if uri:
                out.append({"kind": "text", "text": uri})
    return out


@app.post("/chat")
async def chat(req: Request):
    body = await req.json()
    message = body.get("message", "")
    user_id = body.get("user_id") or "web-user"
    parts: list[dict] = []

    async with httpx.AsyncClient(headers=_auth_headers(), timeout=120) as client:
        card = await _get_card(client)
        factory = ClientFactory(
            ClientConfig(
                supported_transports=[
                    TransportProtocol.jsonrpc,
                    TransportProtocol.http_json,
                ],
                httpx_client=client,
            )
        )
        a2a_client = factory.create(card)

        msg = Message(
            message_id=str(uuid.uuid4()),
            role=Role.user,
            parts=[Part(root=TextPart(text=message))],
            context_id=_contexts.get(user_id),
        )

        last_task = None
        got_artifact_update = False
        async for event in a2a_client.send_message(msg):
            print(f"[DEBUG A2A EVENT] type={type(event)} content={event}")
            task = None
            update = None
            if isinstance(event, tuple) and len(event) == 2:
                task, update = event
            elif hasattr(event, "task"):
                task = event.task
                update = event
            else:
                task = event

            if task is not None:
                last_task = task
                if getattr(task, "context_id", None):
                    _contexts[user_id] = task.context_id

            if update is not None:
                # Check update.artifact
                art = getattr(update, "artifact", None)
                if art and getattr(art, "parts", None):
                    print(f"[DEBUG ARTIFACT PARTS] {art.parts}")
                    parts.extend(_extract_parts(art.parts))

                # Check update.message
                m = getattr(update, "message", None)
                if m and getattr(m, "parts", None):
                    print(f"[DEBUG MESSAGE PARTS] {m.parts}")
                    parts.extend(_extract_parts(m.parts))

                # Check update.parts
                p_list = getattr(update, "parts", None)
                if p_list:
                    print(f"[DEBUG UPDATE PARTS] {p_list}")
                    parts.extend(_extract_parts(p_list))

        # Fallback 1: check last_task.artifacts and history
        if not parts and last_task is not None:
            print(f"[DEBUG FALLBACK LAST_TASK] artifacts={getattr(last_task, 'artifacts', None)} history_len={len(getattr(last_task, 'history', []) or [])}")
            for artifact in getattr(last_task, "artifacts", None) or []:
                if getattr(artifact, "parts", None):
                    parts.extend(_extract_parts(artifact.parts))

            # Fallback 2: check last_task.history
            if not parts and getattr(last_task, "history", None):
                for msg_item in last_task.history:
                    print(f"[DEBUG HISTORY ITEM] role={getattr(msg_item, 'role', None)} parts={getattr(msg_item, 'parts', None)}")
                    role = getattr(msg_item, "role", None)
                    if str(role).lower() in ("agent", "role.agent", "assistant", "model"):
                        parts.extend(_extract_parts(getattr(msg_item, "parts", [])))

            # Fallback 3: fetch complete task via a2a_client.get_task
            if not parts and getattr(last_task, "id", None):
                try:
                    print(f"[DEBUG GET_TASK] Fetching task {last_task.id}...")
                    final_task = await a2a_client.get_task(TaskQueryParams(id=last_task.id, history_length=100))
                    if final_task:
                        print(f"[DEBUG GET_TASK SUCCESS] history_len={len(getattr(final_task, 'history', []) or [])} artifacts={len(getattr(final_task, 'artifacts', []) or [])}")
                        for artifact in getattr(final_task, "artifacts", None) or []:
                            if getattr(artifact, "parts", None):
                                parts.extend(_extract_parts(artifact.parts))
                        if getattr(final_task, "history", None):
                            for msg_item in final_task.history:
                                role = getattr(msg_item, "role", None)
                                if str(role).lower() in ("agent", "role.agent", "assistant", "model"):
                                    parts.extend(_extract_parts(getattr(msg_item, "parts", [])))
                except Exception as ex:
                    print(f"[DEBUG GET_TASK EXCEPTION] {ex}")

        # Deduplicate parts before returning
        seen_parts = set()
        unique_parts = []
        for p in parts:
            p_str = str(p)
            if p_str not in seen_parts:
                seen_parts.add(p_str)
                unique_parts.append(p)
        parts = unique_parts

    if not parts:
        parts = [{"kind": "text", "text": "(The agent didn't return a reply.)"}]
    return JSONResponse({"parts": parts})


app.mount("/", StaticFiles(directory="static", html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
