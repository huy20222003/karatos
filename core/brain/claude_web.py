import httpx
import base64
import json
import time
from typing import Optional, List, Any, Tuple
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    BaseMessage, 
    SystemMessage, 
    HumanMessage, 
    AIMessage
)
from langchain_core.outputs import ChatGeneration, ChatResult
from config.settings import settings
from utils.logger import get_logger
from utils.telemetry import telemetry

logger = get_logger()

class ClaudeWebAdapter(BaseChatModel):
    """
    Shared LangChain adapter for the internal Claude web proxy.
    Supports standard text generation, tool calling, and vision tasks.
    """

    endpoint: str = settings.claude_web_endpoint

    @property
    def _llm_type(self) -> str:
        return "claude_web_shared"

    @property
    def _identifying_params(self) -> dict:
        return {"endpoint": self.endpoint}

    def bind_tools(self, tools: List[Any], **kwargs: Any) -> Any:
        """Bind tools to the model for tool calling."""
        return self.bind(tools=tools, **kwargs)

    def _flatten_messages(self, messages: List[BaseMessage]) -> Tuple[str, List[str]]:
        """
        Extract text prompt and file UUIDs (for vision) from messages.
        """
        parts = []
        file_uuids = []
        
        for m in messages:
            if isinstance(m, SystemMessage):
                parts.append(f"[SYSTEM]\n{m.content}")
            elif isinstance(m, AIMessage):
                parts.append(f"[ASSISTANT]\n{m.content}")
            elif isinstance(m, HumanMessage):
                if isinstance(m.content, str):
                    parts.append(f"[USER]\n{m.content}")
                elif isinstance(m.content, list):
                    user_text = ""
                    for part in m.content:
                        if part.get("type") == "text":
                            user_text += part.get("text", "")
                        elif part.get("type") == "image_url":
                            img_url = part.get("image_url", {}).get("url", "")
                            if "base64," in img_url:
                                header, b64_data = img_url.split("base64,")
                                mime_type = header.split(":")[1].split(";")[0]
                                # Note: Uploading in flattening is tricky for sync, 
                                # so we just mark it and handle in _generate/_agenerate if needed.
                                # But for simplicity and consistency with previous vision_model,
                                # we handle it here if it's async (implied by usage).
                                pass 
                        elif part.get("type") == "image": # Anthropic format
                            source = part.get("source", {})
                            if source.get("type") == "base64":
                                pass
                    parts.append(f"[USER]\n{user_text}")
            else:
                parts.append(str(getattr(m, "content", m)))
                
        return "\n\n".join(parts).strip(), file_uuids

    async def _extract_and_upload_visions(self, messages: List[BaseMessage]) -> List[str]:
        """Async helper to find and upload vision images."""
        file_uuids = []
        for m in messages:
            if isinstance(m, HumanMessage) and isinstance(m.content, list):
                for part in m.content:
                    b64_data = None
                    mime_type = "image/jpeg"
                    
                    if part.get("type") == "image_url":
                        img_url = part.get("image_url", {}).get("url", "")
                        if "base64," in img_url:
                            header, b64_data = img_url.split("base64,")
                            mime_type = header.split(":")[1].split(";")[0]
                    elif part.get("type") == "image":
                        source = part.get("source", {})
                        if source.get("type") == "base64":
                            b64_data = source.get("data")
                            mime_type = source.get("media_type", "image/jpeg")
                    
                    if b64_data:
                        f_uuid = await self._upload_image(b64_data, mime_type)
                        if f_uuid:
                            file_uuids.append(f_uuid)
        return file_uuids

    async def _upload_image(self, b64_data: str, mime_type: str) -> Optional[str]:
        try:
            if "/completion" in self.endpoint:
                base_api = self.endpoint.split("/completion")[0]
            else:
                base_api = self.endpoint.rstrip("/")
                
            upload_url = f"{base_api}/upload-file"
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                img_bytes = base64.b64decode(b64_data)
                files = {"file": ("vision_input.jpg", img_bytes, mime_type)}
                resp = await client.post(upload_url, files=files)
                resp.raise_for_status()
                return resp.json().get("file_uuid")
        except Exception as e:
            logger.error(f"[CLAUDE_WEB_ADAPTER] Failed to upload image: {e}")
            return None

    def _sanitize_payload(self, obj: Any) -> Any:
        """Ensure payload is JSON serializable for httpx."""
        if isinstance(obj, dict):
            return {k: self._sanitize_payload(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._sanitize_payload(v) for v in obj]
        elif hasattr(obj, "__name__") and "Metaclass" in str(type(obj)):
            return str(obj.__name__)
        elif hasattr(obj, "json") and callable(obj.json):
            try: return json.loads(obj.json())
            except: return str(obj)
        return obj

    def _prepare_payload(self, messages: List[BaseMessage], file_uuids: List[str] = None, **kwargs: Any) -> dict:
        prompt, _ = self._flatten_messages(messages)
        payload = {
            "prompt": prompt,
            "model": settings.claude_web_model_name,
            "file_uuids": file_uuids or []
        }
        
        # Add tools if provided
        if "tools" in kwargs:
            raw_tools = kwargs["tools"]
            serialized_tools = []
            for t in raw_tools:
                tool_dict = {
                    "name": getattr(t, "name", str(t)),
                    "description": getattr(t, "description", ""),
                }
                if hasattr(t, "args") and isinstance(t.args, dict):
                    tool_dict["args"] = t.args
                serialized_tools.append(tool_dict)
            payload["tools"] = serialized_tools

        return self._sanitize_payload(payload)

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[list] = None,
        **kwargs,
    ) -> ChatResult:
        # Sync doesn't support vision upload for now (matches existing model.py behavior)
        payload = self._prepare_payload(messages, **kwargs)
        timeout = float(settings.claude_web_timeout_seconds)

        t_start = time.time()
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(self.endpoint, json=payload)
            resp.raise_for_status()
            data = resp.json()
            content = data.get("content", "")
        latency = time.time() - t_start

        if stop:
            for s in stop:
                if s and s in content:
                    content = content.split(s)[0]
                    break

        telemetry.record_interaction(telemetry.estimate_tokens(payload["prompt"] + content), latency)
        ai_msg = AIMessage(content=content)
        return ChatResult(generations=[ChatGeneration(message=ai_msg)])

    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[list] = None,
        **kwargs,
    ) -> ChatResult:
        # 1. Handle Vision Uploads
        file_uuids = await self._extract_and_upload_visions(messages)
        
        # 2. Prepare Payload
        payload = self._prepare_payload(messages, file_uuids=file_uuids, **kwargs)
        timeout = float(settings.claude_web_timeout_seconds)

        # 3. Request Completion
        t_start = time.time()
        async with httpx.AsyncClient(timeout=timeout) as client:
            # Multi-endpoint safety for vision_model.py compatibility
            comp_url = self.endpoint if "/completion" in self.endpoint else f"{self.endpoint.rstrip('/')}/completion"
            
            resp = await client.post(comp_url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            content = data.get("content", "")
        latency = time.time() - t_start

        if stop:
            for s in stop:
                if s and s in content:
                    content = content.split(s)[0]
                    break

        telemetry.record_interaction(telemetry.estimate_tokens(payload["prompt"] + content), latency)
        ai_msg = AIMessage(content=content)
        
        # Attach tool calls if present
        if "tool_calls" in data:
            ai_msg.additional_kwargs["tool_calls"] = data["tool_calls"]
            
        return ChatResult(generations=[ChatGeneration(message=ai_msg)])
