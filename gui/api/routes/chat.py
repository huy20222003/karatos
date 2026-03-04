"""
Chat API Routes — Direct conversation with agent via GUI.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import base64
import asyncio
from utils.logger import get_logger

logger = get_logger()
router = APIRouter()


class ChatMessage(BaseModel):
    message: str = ""
    chat_id: Optional[str] = "gui_session"
    image_base64: Optional[str] = None
    audio_base64: Optional[str] = None
    file_base64: Optional[str] = None
    file_name: Optional[str] = None
    mime_type: Optional[str] = None


@router.post("")
async def send_message(body: ChatMessage):
    """Send a message to the agent and get a response."""
    from gui.server import get_agent

    agent = get_agent()
    if not agent:
        raise HTTPException(503, "Agent not initialized")

    if not body.message.strip() and not body.image_base64 and not body.audio_base64 and not body.file_base64:
        raise HTTPException(400, "Message cannot be empty")

    try:
        context = {
            "sync_execution": True,
            "channel": "gui",
            "image_base64": body.image_base64,
            "mime_type": body.mime_type
        }

        # Process document file if provided
        if body.file_base64 and body.file_name:
            from utils.file_handler import save_temp_data
            try:
                file_bytes = base64.b64decode(body.file_base64)
                temp_file_path = save_temp_data(file_bytes, "file", filename=body.file_name)

                from tools.file_reader import FileReader
                fr_result = await FileReader.execute(file_path=temp_file_path)
                if fr_result.get("status") == "success":
                    file_text = fr_result["data"]["content"]
                    # Inject extracted text into the message for the agent
                    header = f"[User attached file: {body.file_name}]"
                    if body.message.strip():
                        body.message = f"{body.message}\n\n{header}\n{file_text[:32000]}"
                    else:
                        body.message = f"{header}\n{file_text[:32000]}"
                    context["file_path"] = temp_file_path
                    context["file_name"] = body.file_name
                    logger.info(f"[FILE] Extracted {len(file_text)} chars from {body.file_name}")
                else:
                    logger.warning(f"[FILE] Failed to read {body.file_name}: {fr_result.get('message')}")
            except Exception as e:
                logger.error(f"[FILE] Processing exception: {e}")

        # Process audio if provided
        if body.audio_base64:
            from utils.file_handler import save_temp_data
            try:
                # Decode base64 to bytes
                audio_bytes = base64.b64decode(body.audio_base64)
                
                ext = "ogg"
                if body.mime_type and "webm" in body.mime_type.lower():
                    ext = "webm"
                elif body.mime_type and "mp3" in body.mime_type.lower():
                    ext = "mp3"
                elif body.mime_type and "wav" in body.mime_type.lower():
                    ext = "wav"
                
                temp_audio_path = save_temp_data(audio_bytes, "voice", chat_id=body.chat_id, ext=ext)
                
                from tools.audio_processor import AudioProcessor
                tr = await AudioProcessor.execute(file_path=temp_audio_path, language="vi")
                
                if tr.get("status") == "success":
                    transcript = tr.get("data", {}).get("text", "")
                    if transcript and "no speech" not in transcript.lower():
                        context["audio_transcript"] = transcript
                        if not body.message.strip():
                            body.message = transcript
                        else:
                            body.message = f"{body.message}\n\n[VOICE]: {transcript}".strip()
                else:
                    print(f"Audio processing failed: {tr.get('message')}")

                # Inject the file path into the context for tools
                context["file_path"] = temp_audio_path
                # We do NOT delete the file here anymore so that the agent's tools can access it.
            except Exception as e:
                print(f"Audio processing exception: {e}")

        # Process image if provided (save locally for tools/cleanup)
        if body.image_base64:
            from utils.file_handler import save_temp_data
            try:
                img_bytes = base64.b64decode(body.image_base64)
                
                ext = "png"
                if body.mime_type and "jpeg" in body.mime_type.lower():
                    ext = "jpg"
                elif body.mime_type and "webp" in body.mime_type.lower():
                    ext = "webp"
                
                img_path = save_temp_data(img_bytes, "image", chat_id=body.chat_id, ext=ext)
                context["image_path"] = img_path
            except Exception as e:
                logger.error(f"[IMAGE] Local save failed: {e}")

        # ── Fire Cloudinary upload(s) IN PARALLEL with agent.chat() ──
        upload_tasks = []
        from utils.cloudinary_mgr import upload_base64 as cloud_upload

        if body.image_base64:
            upload_tasks.append(cloud_upload(body.image_base64, resource_type="image"))
        else:
            upload_tasks.append(asyncio.sleep(0))  # placeholder

        if body.audio_base64:
            upload_tasks.append(cloud_upload(body.audio_base64, resource_type="video"))
        else:
            upload_tasks.append(asyncio.sleep(0))  # placeholder

        if body.file_base64:
            upload_tasks.append(cloud_upload(body.file_base64, resource_type="raw"))
        else:
            upload_tasks.append(asyncio.sleep(0))  # placeholder

        # Run agent + uploads concurrently
        agent_task = asyncio.create_task(agent.chat(body.message, chat_id=body.chat_id, context=context))
        cloud_results = await asyncio.gather(*upload_tasks, return_exceptions=True)
        result = await agent_task

        # Extract Cloudinary URLs (None if upload failed / not attempted)
        image_url = cloud_results[0] if isinstance(cloud_results[0], str) else None
        audio_url = cloud_results[1] if isinstance(cloud_results[1], str) else None
        file_url = cloud_results[2] if isinstance(cloud_results[2], str) else None

        if image_url:
            logger.info(f"[CLOUDINARY] Image uploaded: {image_url}")
        if audio_url:
            logger.info(f"[CLOUDINARY] Audio uploaded: {audio_url}")
        if file_url:
            logger.info(f"[CLOUDINARY] File uploaded: {file_url}")

        # Patch chat history with lightweight URLs for frontend reload
        # (URLs are ~80 bytes each — NOT heavy base64 blobs)
        try:
            if image_url or audio_url or file_url:
                memory = getattr(agent, 'memory', None)
                if memory:
                    history = await memory.get_chat_history(body.chat_id, limit=2)
                    # Find the last user message to patch
                    for msg in reversed(history):
                        if msg.get("role") == "user":
                            meta = msg.get("metadata", {})
                            if image_url: meta["image_url"] = image_url
                            if audio_url: meta["audio_url"] = audio_url
                            if file_url: meta["file_url"] = file_url
                            if body.file_name: meta["file_name"] = body.file_name
                            msg["metadata"] = meta
                            # Re-save with updated metadata
                            from memory.persistent import MemoryCategory
                            from datetime import datetime as _dt
                            key = f"chat:{body.chat_id}:url_{_dt.utcnow().timestamp()}"
                            await memory.remember(key, msg, category=MemoryCategory.CONTEXT, importance=0.2)
                            logger.info(f"[CLOUDINARY] Patched chat history with URLs")
                            break
        except Exception as e:
            logger.warning(f"[CLOUDINARY] History patch skipped: {e}")

        response_text = ""
        if isinstance(result, dict):
            response_text = result.get("response") or result.get("text") or ""
            # Don't nest 'metadata' if it's already a flat dict in result
            metadata = result.get("metadata") or {}
            
            # Check for WAIT_FOR_APPROVAL status
            if result.get("status") == "WAIT_FOR_APPROVAL":
                metadata["requires_approval"] = True
                metadata["approval_id"] = result.get("approval_id")
        else:
            response_text = str(result)
            metadata = {}

        # Prepare final response and handle image data
        response_data = {
            "response": response_text,
            "metadata": {
                "thoughts": result.get("thoughts", []) if isinstance(result, dict) else [],
                "plan": result.get("plan", []) if isinstance(result, dict) else [],
                "tools_used": result.get("tools_used", []) if isinstance(result, dict) else [],
                "logic": result.get("logic", "") if isinstance(result, dict) else "",
                "decision": result.get("decision", {}).get("action") if isinstance(result, dict) and isinstance(result.get("decision"), dict) else None,
                "approval_id": result.get("approval_id") if isinstance(result, dict) else None,
                "episode_id": result.get("episode_id") if isinstance(result, dict) else None,
                "task_outputs": result.get("task_outputs", []) if isinstance(result, dict) else [],
                **metadata
            }
        }

        # Include Cloudinary URLs in response for frontend to use
        if image_url:
            response_data["image_url"] = image_url
        if audio_url:
            response_data["audio_url"] = audio_url
        if file_url:
            response_data["file_url"] = file_url
            response_data["metadata"]["file_name"] = body.file_name
            response_data["metadata"]["file_url"] = file_url

        # Handle photo/image data for GUI (bytes -> base64)
        if isinstance(result, dict) and result.get("photo"):
            try:
                photo_bytes = result["photo"]
                if isinstance(photo_bytes, bytes):
                    b64_str = base64.b64encode(photo_bytes).decode('utf-8')
                    response_data["photo"] = f"data:image/png;base64,{b64_str}"
            except Exception as e:
                logger.warning(f"[API] Photo conversion failed: {e}")

        return response_data
    except Exception as e:
        logger.error(f"[API] Error in send_message: {e}", exc_info=True)
        return {"error": str(e), "metadata": {}}
    finally:
        from utils.file_handler import cleanup_temp_file
        if context:
            cleanup_temp_file(context.get("file_path"), source="AGENT_CHAT")
            cleanup_temp_file(context.get("image_path"), source="AGENT_CHAT")


from fastapi.responses import StreamingResponse
import json
import asyncio
from utils.helpers import safe_json_dumps

@router.post("/stream")
async def stream_message(body: ChatMessage):
    """Stream a message to the agent and receive SSE events."""
    from gui.server import get_agent
    from utils.logger import get_logger
    logger = get_logger()

    agent = get_agent()
    if not agent:
        raise HTTPException(503, "Agent not initialized")

    if not body.message.strip() and not body.image_base64 and not body.audio_base64 and not body.file_base64:
        raise HTTPException(400, "Message cannot be empty")

    context = {
        "sync_execution": True,
        "channel": "gui",
        "image_base64": body.image_base64,
        "audio_base64": body.audio_base64,
        "mime_type": body.mime_type
    }

    # Process document file if provided
    if body.file_base64 and body.file_name:
        from utils.file_handler import save_temp_data
        try:
            file_bytes = base64.b64decode(body.file_base64)
            temp_file_path = save_temp_data(file_bytes, "file", filename=body.file_name)

            from tools.file_reader import FileReader
            fr_result = await FileReader.execute(file_path=temp_file_path)
            if fr_result.get("status") == "success":
                file_text = fr_result["data"]["content"]
                header = f"[User attached file: {body.file_name}]"
                if body.message.strip():
                    body.message = f"{body.message}\n\n{header}\n{file_text[:32000]}"
                else:
                    body.message = f"{header}\n{file_text[:32000]}"
                context["file_path"] = temp_file_path
                context["file_name"] = body.file_name
                logger.info(f"[FILE/STREAM] Extracted {len(file_text)} chars from {body.file_name}")
        except Exception as e:
            logger.error(f"[FILE/STREAM] Processing exception: {e}")

    # Audio processing same as normal endpoint
    if body.audio_base64:
        from utils.file_handler import save_temp_data
        try:
            audio_bytes = base64.b64decode(body.audio_base64)
            
            ext = "ogg"
            if body.mime_type and "webm" in body.mime_type.lower():
                ext = "webm"
            elif body.mime_type and "mp3" in body.mime_type.lower():
                ext = "mp3"
            elif body.mime_type and "wav" in body.mime_type.lower():
                ext = "wav"
            
            temp_audio_path = save_temp_data(audio_bytes, "voice", chat_id=body.chat_id, ext=ext)
            
            from tools.audio_processor import AudioProcessor
            tr = await AudioProcessor.execute(file_path=temp_audio_path, language="vi")
            
            if tr.get("status") == "success":
                transcript = tr.get("data", {}).get("text", "")
                if transcript and "no speech" not in transcript.lower():
                    context["audio_transcript"] = transcript
                    if not body.message.strip():
                        body.message = transcript
                    else:
                        body.message = f"{body.message}\n\n[VOICE]: {transcript}".strip()
            
                # Inject the file path into the context for tools
                context["file_path"] = temp_audio_path
                # We do NOT delete the file here anymore so that the agent's tools can access it.
        except Exception as e:
            logger.error(f"Audio stream processing exception: {e}")

    # Process image if provided (save locally for tools/cleanup)
    if body.image_base64:
        from utils.file_handler import save_temp_data
        try:
            img_bytes = base64.b64decode(body.image_base64)
            
            ext = "png"
            if body.mime_type and "jpeg" in body.mime_type.lower():
                ext = "jpg"
            elif body.mime_type and "webp" in body.mime_type.lower():
                ext = ".webp"
            
            img_path = save_temp_data(img_bytes, "image", chat_id=body.chat_id, ext=ext)
            context["image_path"] = img_path
        except Exception as e:
            logger.error(f"[IMAGE/STREAM] Local save failed: {e}")

    # Fire-and-forget Cloudinary upload for streaming
    async def _background_cloud_upload():
        try:
            from utils.cloudinary_mgr import upload_base64 as cloud_upload
            image_url, audio_url, file_url = None, None, None
            if body.image_base64:
                image_url = await cloud_upload(body.image_base64, resource_type="image")
                if image_url: logger.info(f"[CLOUDINARY/STREAM] Image uploaded: {image_url}")
            if body.audio_base64:
                audio_url = await cloud_upload(body.audio_base64, resource_type="video")
                if audio_url: logger.info(f"[CLOUDINARY/STREAM] Audio uploaded: {audio_url}")
            if body.file_base64:
                file_url = await cloud_upload(body.file_base64, resource_type="raw")
                if file_url: logger.info(f"[CLOUDINARY/STREAM] File uploaded: {file_url}")
            # Patch chat history with URLs for reload
            if image_url or audio_url or file_url:
                memory = getattr(agent, 'memory', None)
                if memory:
                    history = await memory.get_chat_history(body.chat_id, limit=2)
                    for msg in reversed(history):
                        if msg.get("role") == "user":
                            meta = msg.get("metadata", {})
                            if image_url: meta["image_url"] = image_url
                            if audio_url: meta["audio_url"] = audio_url
                            if file_url: meta["file_url"] = file_url
                            if body.file_name: meta["file_name"] = body.file_name
                            msg["metadata"] = meta
                            from memory.persistent import MemoryCategory
                            from datetime import datetime as _dt
                            key = f"chat:{body.chat_id}:url_{_dt.utcnow().timestamp()}"
                            await memory.remember(key, msg, category=MemoryCategory.CONTEXT, importance=0.2)
                            logger.info(f"[CLOUDINARY/STREAM] Patched chat history with URLs")
                            break
        except Exception as e:
            logger.warning(f"[CLOUDINARY/STREAM] Background upload failed: {e}")

    if body.image_base64 or body.audio_base64 or body.file_base64:
        asyncio.create_task(_background_cloud_upload())

    async def event_generator():
        try:
            async for event in agent.chat_stream(body.message, chat_id=body.chat_id, context=context):
                # Handle photo bytes in stream events (usually in final_response)
                if event.get("type") == "final_response" and isinstance(event.get("data"), dict):
                    photo = event["data"].get("photo")
                    if isinstance(photo, bytes):
                        try:
                            b64 = base64.b64encode(photo).decode('utf-8')
                            event["data"]["photo"] = f"data:image/png;base64,{b64}"
                        except: pass
                
                yield f"data: {safe_json_dumps(event)}\n\n"
        except Exception as e:
            logger.error(f"[API] Stream generator error: {e}", exc_info=True)
            yield f"data: {safe_json_dumps({'type': 'error', 'message': str(e)})}\n\n"
        finally:
            from utils.file_handler import cleanup_temp_file
            if context:
                cleanup_temp_file(context.get("file_path"), source="AGENT_STREAM")
                cleanup_temp_file(context.get("image_path"), source="AGENT_STREAM")

    return StreamingResponse(event_generator(), media_type="text/event-stream")



from pydantic import BaseModel

class ApprovalRequest(BaseModel):
    id: str
    action: str

@router.post("/approve")
async def handle_gui_approval(req: ApprovalRequest):
    """Handle approval/denial from the GUI."""
    try:
        from utils.notification import NotificationManager
        from gui.server import get_agent
        
        agent = get_agent()
        if not agent:
            return {"error": "Agent not initialized"}
            
        callback_data = f"cli_{req.action.lower()}:{req.id}"
        
        # We need a dummy "channel" because handle_approval_callback expects one
        # but only for answer_callback_query which we guard against.
        class DummyChannel:
            async def send(self, msg, recipient=None):
                logger.info(f"[GUI_APPROVAL] Notification: {msg}")
                return True
        
        response = await NotificationManager.handle_approval_callback(
            data=callback_data,
            channel=DummyChannel(),
            sender_id="GUI",
            callback_id=None
        )
        
        return {"status": "success", "message": response}
    except Exception as e:
        logger.error(f"[API] Approval error: {e}")
        return {"error": str(e)}


@router.get("/history")
async def get_history():
    """Get recent conversation history."""
    from gui.server import get_agent

    agent = get_agent()
    if not agent:
        return {"messages": []}

    try:
        # Load from persistent memory
        history = await agent.memory.get_chat_history("gui_session")
        return {"messages": history}
    except Exception as e:
        logger.error(f"[API] History error: {e}")
        pass

    return {"messages": []}
