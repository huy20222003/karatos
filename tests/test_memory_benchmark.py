"""
Memory & Distiller Test Suite
Tests:
1. Memory retrieval speed (nearest → farthest, BM25 ranking)
2. Deduplication engine (Jaccard similarity)
3. Knowledge condensation (consolidate_memories + extract_essence)

Run: python tests/test_memory_benchmark.py
"""
import asyncio
import time
import sys
import os
import json

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def test_memory_retrieval_speed():
    """Test 1: Memory retrieval speed and context understanding"""
    from memory.persistent import PersistentMemory, MemoryCategory
    
    print("=" * 70)
    print("TEST 1: Memory Retrieval Speed & Context Understanding")
    print("=" * 70)
    
    mem = PersistentMemory(base_path="data/storage")
    
    # --- Phase A: Store test memories (nearest → farthest) ---
    print("\n📝 Phase A: Storing test memories...")
    test_memories = [
        # Recent (high importance)
        ("test:recent:1", "User Huy prefers dark mode and Vietnamese language", MemoryCategory.USER_PROFILE, 0.9),
        ("test:recent:2", "The API gateway is running on port 3000", MemoryCategory.SYSTEM, 0.8),
        ("test:recent:3", "Last deployment was successful with zero downtime", MemoryCategory.EXPERIENCE, 0.7),
        # Mid-range
        ("test:mid:1", "PostgreSQL query optimization: always use indexes on foreign keys", MemoryCategory.LEARNING, 0.8),
        ("test:mid:2", "User asked about NestJS migration strategy last week", MemoryCategory.CONTEXT, 0.5),
        # Old (low importance)
        ("test:old:1", "First system boot was on January 15 2025", MemoryCategory.METADATA, 0.3),
        ("test:old:2", "Early tests showed memory leak in websocket handler", MemoryCategory.REFLECTION, 0.6),
    ]
    
    store_times = []
    for key, value, category, importance in test_memories:
        t0 = time.perf_counter()
        result = await mem.remember(key, value, category=category, importance=importance)
        t1 = time.perf_counter()
        store_times.append((t1 - t0) * 1000)
        print(f"  ✅ Stored: {key} ({(t1-t0)*1000:.1f}ms) → {result}")
    
    avg_store = sum(store_times) / len(store_times)
    print(f"\n⏱️  Average store time: {avg_store:.1f}ms")
    
    # --- Phase B: Retrieval tests ---
    print("\n🔍 Phase B: Retrieval Tests...")
    
    queries = [
        ("dark mode Vietnamese", "Should find user preference"),
        ("PostgreSQL optimization indexes", "Should find learning about DB"),
        ("API gateway port", "Should find system info"),
        ("deployment success", "Should find experience"),
        ("memory leak websocket", "Should find old reflection"),
        ("NestJS migration", "Should find context"),
    ]
    
    retrieval_times = []
    for query, expected in queries:
        t0 = time.perf_counter()
        results = await mem.deep_recall(query, limit=5)
        t1 = time.perf_counter()
        elapsed = (t1 - t0) * 1000
        retrieval_times.append(elapsed)
        
        print(f"\n  🔎 Query: \"{query}\" ({elapsed:.1f}ms)")
        print(f"     Expected: {expected}")
        if results:
            top = results[0]
            print(f"     Top result: [{top.category.value}] {top.key} (score: {top.score:.2f}, importance: {top.importance})")
            print(f"     Value: {str(top.value)[:80]}...")
        else:
            print(f"     ⚠️  No results found!")
    
    avg_retrieval = sum(retrieval_times) / len(retrieval_times)
    max_retrieval = max(retrieval_times)
    min_retrieval = min(retrieval_times)
    
    print(f"\n{'=' * 50}")
    print(f"📊 RETRIEVAL PERFORMANCE SUMMARY")
    print(f"{'=' * 50}")
    print(f"  Min: {min_retrieval:.1f}ms")
    print(f"  Avg: {avg_retrieval:.1f}ms")
    print(f"  Max: {max_retrieval:.1f}ms")
    print(f"  Queries tested: {len(queries)}")
    
    return avg_retrieval


async def test_deduplication():
    """Test 2: Deduplication engine"""
    from memory.persistent import PersistentMemory, MemoryCategory
    
    print("\n" + "=" * 70)
    print("TEST 2: Deduplication Engine")
    print("=" * 70)
    
    mem = PersistentMemory(base_path="data/storage")
    
    # Store original
    r1 = await mem.remember(
        "test:dedup:original",
        "PostgreSQL query optimization requires proper indexing on foreign keys for performance",
        category=MemoryCategory.LEARNING,
        importance=0.8
    )
    print(f"  Original stored: {r1}")
    
    # Store duplicate (similar content)
    r2 = await mem.remember(
        "test:dedup:duplicate",
        "PostgreSQL optimization involves indexing foreign keys to improve query performance",
        category=MemoryCategory.LEARNING,
        importance=0.7
    )
    print(f"  Duplicate attempt: {r2}")
    
    # Store different (should NOT be deduped)
    r3 = await mem.remember(
        "test:dedup:different",
        "Python asyncio event loop handles concurrent I/O operations efficiently",
        category=MemoryCategory.LEARNING,
        importance=0.6
    )
    print(f"  Different stored: {r3}")
    
    is_deduped = "dedup" in r2
    is_stored = "dedup" not in r3
    
    print(f"\n  📊 Duplicate detected: {'✅ YES' if is_deduped else '❌ NO'}")
    print(f"  📊 Different stored:  {'✅ YES' if is_stored else '❌ NO'}")


async def test_knowledge_condensation():
    """Test 3: Knowledge condensation (consolidate + extract_essence)"""
    from utils.distiller import MemoryDistiller
    
    print("\n" + "=" * 70)
    print("TEST 3: Knowledge Condensation")
    print("=" * 70)
    
    distiller = MemoryDistiller()
    
    # Test data: related facts that should be consolidated
    test_memories = [
        {"key": "fact1", "value": "User Huy likes dark mode UI", "category": "USER_PROFILE", "importance": 0.8},
        {"key": "fact2", "value": "User Huy prefers Vietnamese language for responses", "category": "USER_PROFILE", "importance": 0.9},
        {"key": "fact3", "value": "User Huy's preferred language is Vietnamese", "category": "USER_PROFILE", "importance": 0.7},
        {"key": "fact4", "value": "The API runs on port 3000", "category": "SYSTEM", "importance": 0.8},
        {"key": "fact5", "value": "Gateway service port is 3000", "category": "SYSTEM", "importance": 0.6},
        {"key": "fact6", "value": "PostgreSQL indexes improve query speed", "category": "LEARNING", "importance": 0.7},
        {"key": "fact7", "value": "Always use indexes on foreign keys in PostgreSQL", "category": "LEARNING", "importance": 0.8},
        {"key": "fact8", "value": "PostgreSQL performance depends on proper indexing", "category": "LEARNING", "importance": 0.6},
    ]
    
    print(f"\n  📥 Input: {len(test_memories)} raw facts")
    
    # --- Test consolidation (Layer 2) ---
    print("\n  🔄 Running consolidation (Layer 2)...")
    t0 = time.perf_counter()
    try:
        consolidated = await distiller.consolidate_memories(test_memories, topic="Agent Knowledge")
        t1 = time.perf_counter()
        
        print(f"  ⏱️  Consolidation time: {(t1-t0)*1000:.0f}ms")
        print(f"  📊 Result: {len(test_memories)} → {len(consolidated)} facts ({100 - len(consolidated)/len(test_memories)*100:.0f}% reduction)")
        
        for i, item in enumerate(consolidated):
            print(f"    [{item.get('category', '?')}] {item.get('value', '?')[:80]}... (imp: {item.get('importance', '?')})")
    except Exception as e:
        print(f"  ⚠️  Consolidation failed (LLM may not be available): {e}")
        consolidated = test_memories
    
    # --- Test essence extraction (Layer 3) ---
    print("\n  💎 Running essence extraction (Layer 3)...")
    t0 = time.perf_counter()
    try:
        beliefs = await distiller.extract_essence(consolidated, max_beliefs=5)
        t1 = time.perf_counter()
        
        print(f"  ⏱️  Extraction time: {(t1-t0)*1000:.0f}ms")
        print(f"  📊 Core beliefs extracted: {len(beliefs)}")
        
        for i, b in enumerate(beliefs):
            print(f"    {i+1}. [{b.get('category', '?')}] {b.get('belief', '?')} (imp: {b.get('importance', '?')})")
    except Exception as e:
        print(f"  ⚠️  Essence extraction failed (LLM may not be available): {e}")


async def main():
    print("🧠 KARATOS MEMORY & COGNITION BENCHMARK")
    print("=" * 70)
    print(f"Start time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Test 1: Memory retrieval
    avg_time = await test_memory_retrieval_speed()
    
    # Test 2: Deduplication
    await test_deduplication()
    
    # Test 3: Knowledge condensation (requires LLM)
    await test_knowledge_condensation()
    
    print("\n" + "=" * 70)
    print("🏁 ALL TESTS COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
