"""
Investigation Context
Manages the context for deep-dive investigations
"""
from datetime import datetime
from typing import Any, Optional
from dataclasses import dataclass, field
from enum import Enum


class InvestigationStatus(Enum):
    """Status of an investigation"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    AWAITING_DECISION = "awaiting_decision"
    COMPLETED = "completed"
    ESCALATED = "escalated"


@dataclass
class Evidence:
    """A piece of evidence collected during investigation"""
    source: str  # database, api, audit_log
    data: Any
    collected_at: datetime = field(default_factory=datetime.utcnow)
    relevance_score: float = 0.5  # 0-1, how relevant to the investigation


@dataclass
class Investigation:
    """An ongoing investigation into a suspicious entity"""
    id: str
    target_type: str  # user, ip, track, etc.
    target_id: str
    trigger_rule: str  # Which rule triggered this investigation
    status: InvestigationStatus = InvestigationStatus.PENDING
    
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    
    evidence: list[Evidence] = field(default_factory=list)
    thoughts: list[str] = field(default_factory=list)
    
    conclusion: Optional[str] = None
    recommended_action: Optional[str] = None
    action_taken: Optional[str] = None
    
    def add_evidence(self, source: str, data: Any, relevance: float = 0.5):
        """Add evidence to the investigation"""
        self.evidence.append(Evidence(
            source=source,
            data=data,
            relevance_score=relevance
        ))
    
    def add_thought(self, thought: str):
        """Record a thought during investigation"""
        self.thoughts.append(f"[{datetime.utcnow().strftime('%H:%M:%S')}] {thought}")
    
    def complete(self, conclusion: str, action: str = None):
        """Mark investigation as complete"""
        self.status = InvestigationStatus.COMPLETED
        self.completed_at = datetime.utcnow()
        self.conclusion = conclusion
        self.recommended_action = action
    
    def escalate(self, reason: str):
        """Escalate investigation to human review"""
        self.status = InvestigationStatus.ESCALATED
        self.add_thought(f"ESCALATED: {reason}")
    
    def get_summary(self) -> dict:
        """Get investigation summary"""
        return {
            "id": self.id,
            "target": f"{self.target_type}:{self.target_id}",
            "status": self.status.value,
            "evidence_count": len(self.evidence),
            "duration_seconds": (
                (self.completed_at or datetime.utcnow()) - self.started_at
            ).total_seconds(),
            "conclusion": self.conclusion,
            "action": self.action_taken or self.recommended_action
        }


class InvestigationContext:
    """
    Manages active and completed investigations.
    """
    
    def __init__(self, max_active: int = 10, max_history: int = 100):
        self.max_active = max_active
        self.max_history = max_history
        
        self._active: dict[str, Investigation] = {}
        self._completed: list[Investigation] = []
        self._investigation_counter = 0
    
    def _generate_id(self) -> str:
        """Generate a unique investigation ID"""
        self._investigation_counter += 1
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        return f"INV-{timestamp}-{self._investigation_counter:04d}"
    
    def start_investigation(
        self,
        target_type: str,
        target_id: str,
        trigger_rule: str
    ) -> Investigation:
        """Start a new investigation"""
        # Check if already investigating this target
        existing = self.get_active_by_target(target_type, target_id)
        if existing:
            return existing
        
        # Check capacity
        if len(self._active) >= self.max_active:
            # Complete oldest investigation
            oldest_id = min(
                self._active.keys(),
                key=lambda k: self._active[k].started_at
            )
            self._complete_investigation(oldest_id, "Auto-closed: capacity limit")
        
        investigation = Investigation(
            id=self._generate_id(),
            target_type=target_type,
            target_id=target_id,
            trigger_rule=trigger_rule,
            status=InvestigationStatus.IN_PROGRESS
        )
        
        self._active[investigation.id] = investigation
        return investigation
    
    def get_active(self, investigation_id: str) -> Optional[Investigation]:
        """Get an active investigation by ID"""
        return self._active.get(investigation_id)
    
    def get_active_by_target(
        self,
        target_type: str,
        target_id: str
    ) -> Optional[Investigation]:
        """Get active investigation for a specific target"""
        for inv in self._active.values():
            if inv.target_type == target_type and inv.target_id == target_id:
                return inv
        return None
    
    def get_all_active(self) -> list[Investigation]:
        """Get all active investigations"""
        return list(self._active.values())
    
    def complete_investigation(
        self,
        investigation_id: str,
        conclusion: str,
        action: str = None
    ):
        """Complete an investigation"""
        if investigation_id not in self._active:
            return
        
        investigation = self._active[investigation_id]
        investigation.complete(conclusion, action)
        self._complete_investigation(investigation_id, conclusion)
    
    def _complete_investigation(self, investigation_id: str, conclusion: str):
        """Internal method to move investigation to completed"""
        if investigation_id not in self._active:
            return
        
        investigation = self._active.pop(investigation_id)
        if investigation.status != InvestigationStatus.COMPLETED:
            investigation.complete(conclusion)
        
        self._completed.append(investigation)
        
        # Trim history
        while len(self._completed) > self.max_history:
            self._completed.pop(0)
    
    def get_recent_completed(self, count: int = 10) -> list[Investigation]:
        """Get recently completed investigations"""
        return self._completed[-count:]
    
    def get_statistics(self) -> dict:
        """Get investigation statistics"""
        return {
            "active_count": len(self._active),
            "completed_count": len(self._completed),
            "total_started": self._investigation_counter
        }

class ConversationContextManager:
    """
    Unified Manager for conversation context, history optimization, and neural compression.
    Ensures prompt sizes stay within safe limits while preserving reasoning capacity.
    """
    def __init__(self, char_limit_per_message: int = 8000, total_history_limit: int = 20000):
        self.char_limit_per_message = char_limit_per_message
        self.total_history_limit = total_history_limit
        from utils.logger import get_logger
        self.logger = get_logger()

    def truncate_text(self, text: str, limit: int) -> str:
        """Hard char-level truncation for safety."""
        if not text or len(text) <= limit:
            return text
        return text[:limit] + "... [TRUNCATED]"

    async def get_optimized_history(self, chat_id: str, memory_engine: Any, limit: int = 10, episode_id: str = None) -> str:
        """
        Fetches history and formats it as "Summary + N Recent Messages".
        Ensures strict character limits per message. Filtered by episode if provided.
        """
        try:
            # 1. Fetch raw history
            raw_history = await memory_engine.get_chat_history(chat_id, limit=limit)
            if not raw_history:
                return ""

            # Brain 2.6: Filter by Episode
            if episode_id:
                raw_history = [msg for msg in raw_history if msg.get("metadata", {}).get("episode_id") == episode_id]

            # 2. Check for summary-only mode if history is too old (logic handled by memory engine usually)
            # But here we enforce char limits per message
            optimized_lines = []
            current_total = 0
            
            # Process in reverse (most recent first) to prioritize fresh context
            for msg in reversed(raw_history):
                role = str(msg.get("role", "user")).upper()
                content = str(msg.get("content", ""))
                
                # Truncate large individual messages (like previous result tables)
                safe_content = self.truncate_text(content, self.char_limit_per_message)
                line = f"{role}: {safe_content}"
                
                if current_total + len(line) > self.total_history_limit:
                    break
                
                optimized_lines.insert(0, line)
                current_total += len(line)
            
            return "\n".join(optimized_lines)
        except Exception as e:
            self.logger.error(f"[CONTEXT] Error optimizing history: {e}")
            return ""

    async def compress_large_context(self, text: str, model_provider: Any, prompt_registry: Any, query: str = "", prompt_key: str = "persona.tasks.compression") -> str:
        self.model_provider = model_provider
        """
        Uses an Associative Cognitive strategy to compress large text.
        Preserves 'Anchor Points' relevant to the current query while summarizing gaps.
        Bypasses LLM for massive data blocks to ensure CPU responsiveness.
        """
        if not text or len(text) < 15000:
            return text
            
        original_len = len(text)
        
        # --- Phase 27: Associative Cognitive Compression ---
        # Deterministic Bypassing for Speed (CPU Friendly)
        self.logger.info(f"[CONTEXT] Applying Associative Compression (Anchors from: '{query[:30]}...')")
        
        compressed_text = self.associative_compress(text, query)
        
        # If the associative compression didn't reduce it enough (or no query provided),
        # only then do we consider LLM summarization for shorted blocks.
        if len(compressed_text) > 20000 and len(compressed_text) < original_len * 0.5:
             # Already reduced significantly by structural rules, return it
             self.logger.info(f"[CONTEXT] Structural reduction successful: {original_len} -> {len(compressed_text)} chars.")
             return compressed_text

        # LLM Summary Fallback
        if len(compressed_text) > 4000:
            import asyncio
            try:
                # If it's extremely large (>30k), use hierarchical summarization
                if len(compressed_text) > 30000:
                    self.logger.info(f"[CONTEXT] Context extremely large ({len(compressed_text)} chars). Triggering Hierarchical Summarization.")
                    summary_text = await self.hierarchical_compress(compressed_text, model_provider, prompt_registry, prompt_key=prompt_key)
                else:
                    self.logger.info(f"[CONTEXT] Minor Neural refinement for remaining context...")
                    compression_prompt = prompt_registry.get(prompt_key, history_text=compressed_text)
                    summary = await asyncio.wait_for(self.model_provider.ainvoke(compression_prompt), timeout=300.0)
                    
                    from core.brain.utils import get_llm_content
                    summary_text = get_llm_content(summary)
                
                self.logger.info(f"[CONTEXT] Neural refinement complete: {len(compressed_text)} -> {len(summary_text)} chars.")
                return f"### ASSOCIATIVE SUMMARY:\n{summary_text}\n"
            except Exception as e:
                self.logger.warning(f"[CONTEXT] Neural refinement failed: {e}. Falling back to hard truncation.")
                # Hard fallback: Truncate to safe limit (e.g. 8000 chars)
                return f"### RAW DATA (TRUNCATED):\n{compressed_text[:8000]}... [REMAINING DATA OMITTED DUE TO SIZE]"
        
        return compressed_text

    async def hierarchical_compress(self, text: str, model_provider: Any, prompt_registry: Any, chunk_size: int = 8000, prompt_key: str = "persona.tasks.compression") -> str:
        """
        Semantic Hierarchical Compression: Divide text into semantically coherent chunks,
        summarize each, then merge. Uses sentence/paragraph boundaries instead of 
        character-level splitting (textwrap.wrap) to preserve meaning.
        """
        import re
        import asyncio
        
        # 1. Semantic chunking — split at paragraph/sentence boundaries
        chunks = self._semantic_chunk(text, chunk_size)
        self.logger.info(f"[CONTEXT] Hierarchical: {len(text)} chars → {len(chunks)} semantic chunks.")
        
        # 2. Summarize chunks in parallel batches (max 3 concurrent)
        summaries = []
        batch_size = 3
        for batch_start in range(0, len(chunks), batch_size):
            batch = chunks[batch_start:batch_start + batch_size]
            tasks = []
            for i, chunk in enumerate(batch):
                idx = batch_start + i + 1
                self.logger.info(f"[CONTEXT] Summarizing chunk {idx}/{len(chunks)}...")
                prompt = prompt_registry.get(prompt_key, history_text=chunk)
                tasks.append(asyncio.wait_for(model_provider.ainvoke(prompt), timeout=120.0))
            
            try:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                from core.brain.utils import get_llm_content
                for r in results:
                    if isinstance(r, Exception):
                        self.logger.warning(f"[CONTEXT] Chunk summarization failed: {r}")
                        summaries.append(chunk[:1000] + "... [CHUNK SUMMARY FAILED]")
                    else:
                        summaries.append(get_llm_content(r))
            except Exception as e:
                self.logger.warning(f"[CONTEXT] Batch summarization failed: {e}")
                for chunk in batch:
                    summaries.append(chunk[:1000] + "... [CHUNK SUMMARY FAILED]")
        
        combined_summaries = "\n\n".join(summaries)
        if len(combined_summaries) > 5000:
             # Final meta-summary
             self.logger.info(f"[CONTEXT] Final meta-summarization of {len(combined_summaries)} chars...")
             try:
                 prompt = prompt_registry.get(prompt_key, history_text=combined_summaries)
                 final_resp = await asyncio.wait_for(model_provider.ainvoke(prompt), timeout=180.0)
                 from core.brain.utils import get_llm_content
                 return get_llm_content(final_resp)
             except Exception as e:
                 self.logger.warning(f"[CONTEXT] Meta-summarization failed: {e}")
                 return combined_summaries[:5000] + "... [META-SUMMARY FAILED]"
        
        return combined_summaries

    def _semantic_chunk(self, text: str, max_chunk_size: int = 8000) -> list[str]:
        """
        Split text into semantically coherent chunks at natural boundaries.
        Priority: paragraph breaks > sentence endings > clause boundaries.
        """
        import re
        
        # Split into paragraphs first
        paragraphs = re.split(r'\n\s*\n', text)
        
        chunks = []
        current_chunk = []
        current_size = 0
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            
            para_len = len(para)
            
            # If single paragraph exceeds limit, split by sentences
            if para_len > max_chunk_size:
                if current_chunk:
                    chunks.append('\n\n'.join(current_chunk))
                    current_chunk = []
                    current_size = 0
                
                # Split long paragraph by sentences
                sentences = re.split(r'(?<=[.!?。])\s+', para)
                sent_chunk = []
                sent_size = 0
                for sent in sentences:
                    if sent_size + len(sent) > max_chunk_size and sent_chunk:
                        chunks.append(' '.join(sent_chunk))
                        sent_chunk = []
                        sent_size = 0
                    sent_chunk.append(sent)
                    sent_size += len(sent)
                if sent_chunk:
                    chunks.append(' '.join(sent_chunk))
                continue
            
            # If adding this paragraph exceeds limit, start new chunk
            if current_size + para_len > max_chunk_size and current_chunk:
                chunks.append('\n\n'.join(current_chunk))
                current_chunk = []
                current_size = 0
            
            current_chunk.append(para)
            current_size += para_len
        
        # Don't forget the last chunk
        if current_chunk:
            chunks.append('\n\n'.join(current_chunk))
        
        return chunks if chunks else [text[:max_chunk_size]]


    def associative_compress(self, text: str, query: str) -> str:
        """
        Human-like pruning: Keeps what's relevant to the query, fades the rest.
        """
        import re
        lines = text.split('\n')
        if len(lines) < 20: return text
        
        # 1. Extract Anchors (Keywords from query)
        # Avoid language-specific stopword lists; rely on length + later uniqueness filtering.
        anchors = [w.lower() for w in re.findall(r'\w+', query) if len(w) > 3]
        
        if not anchors:
            # Fallback to structural sampling if no query anchors
            return self._structural_sample(lines)

        # 2. Score Lines (Two Pass - Frequency Filtering)
        # Pass 1: Count occurrences to find "Specific" anchors vs "Common" anchors
        raw_patterns = [re.compile(fr'\b{re.escape(a)}\b', re.IGNORECASE) for a in anchors]
        anchor_counts = {a: 0 for a in anchors}
        
        for line in lines:
            line_lower = line.lower()
            for i, a in enumerate(anchors):
                if raw_patterns[i].search(line_lower):
                    anchor_counts[a] += 1
        
        # Keep only anchors that appear in < 10% of lines (uniqueness) 
        # OR if it's the only anchor we have
        threshold = max(2, len(lines) // 10)
        specific_anchors = [a for a in anchors if anchor_counts[a] <= threshold]
        
        # If all anchors are common (e.g. user just said "list everything"), 
        # fall back to structural sampling
        if not specific_anchors:
            self.logger.debug(f"[CONTEXT] All anchors are common. Falling back to structural sampling.")
            return self._structural_sample(lines)
            
        # Pass 2: Mark hits based on specific anchors
        hits = []
        final_patterns = [re.compile(fr'\b{re.escape(a)}\b', re.IGNORECASE) for a in specific_anchors]
        for i, line in enumerate(lines):
            if any(p.search(line) for p in final_patterns):
                hits.append(i)
        
        if not hits:
            return self._structural_sample(lines)

        # 3. Build Windows (Keep 2 lines around hits)
        keep_indices = set()
        window_size = 2
        for h in hits:
            for offset in range(-window_size, window_size + 1):
                idx = h + offset
                if 0 <= idx < len(lines):
                    keep_indices.add(idx)
        
        # Always keep the first 2 lines (often headers)
        keep_indices.add(0)
        keep_indices.add(1)
        
        # 4. Construct Output with Gaps
        output = []
        sorted_indices = sorted(list(keep_indices))
        last_idx = -1
        
        for idx in sorted_indices:
            if idx > last_idx + 1:
                gap_size = idx - last_idx - 1
                if gap_size > 1:
                    output.append(f"   [... {gap_size} lines of non-matching data omitted for speed ...]")
                elif gap_size == 1:
                    output.append(lines[last_idx + 1])
            
            output.append(lines[idx])
            last_idx = idx
            
        if last_idx < len(lines) - 1:
            output.append(f"   [... {len(lines) - last_idx - 1} remaining lines omitted ...]")
            
        final_text = "\n".join(output)
        return f"<associative_memory query_focus=\"{', '.join(anchors)}\">\n{final_text}\n</associative_memory>"

    def _structural_sample(self, lines: list[str]) -> str:
        """Fallback: Sample first, middle, and last lines for large unstructured blocks."""
        if len(lines) <= 20: return "\n".join(lines)
        
        total = len(lines)
        # Keep first 5, last 5, and 3 from the middle
        mid = total // 2
        indices = set(range(0, 5)) | set(range(mid-1, mid+2)) | set(range(total-5, total))
        
        output = []
        last_idx = -1
        for idx in sorted(list(indices)):
            if idx > last_idx + 1:
                output.append(f"   [... {idx - last_idx - 1} items collapsed ...]")
            output.append(lines[idx])
            last_idx = idx
            
        return "\n".join(output)
