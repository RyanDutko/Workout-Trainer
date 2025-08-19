
#!/usr/bin/env python3

from conversation_store import ConversationStore
from ai_service_v2 import AIServiceV2
from models import Database

def test_conversation_memory():
    """Test the 4-layer conversation memory system"""
    
    print("🧪 Testing Conversation Memory System")
    print("=" * 50)
    
    # Initialize components
    db = Database()
    store = ConversationStore()
    ai_service = AIServiceV2(db)
    
    print("✅ Components initialized")
    
    # Test 1: Short-term window
    print("\n📝 Test 1: Short-term conversation window")
    store.append_turn("show me last Thursday logs", "Here are your Thursday workouts: ...")
    store.append_turn("how many sets did I do?", "You did 12 total sets across all exercises.")
    
    window = store.get_recent_window(max_turns=4)
    print(f"Recent window (should show 2 turns):\n{window}")
    
    # Test 2: Pinned facts
    print("\n📌 Test 2: Pinned facts")
    store.set_pinned_fact("goal", "muscle building and strength")
    store.set_pinned_fact("injury", "left shoulder issue - avoid overhead press")
    store.set_pinned_fact("equipment", "home gym with dumbbells and cables")
    
    facts = store.get_pinned_facts()
    print(f"Pinned facts: {facts}")
    
    # Test 3: Semantic recall
    print("\n🔍 Test 3: Semantic recall")
    store.append_turn("my left shoulder was bugging me", "Let's modify your overhead movements to be shoulder-friendly")
    store.append_turn("what substitution for overhead press?", "Try seated dumbbell press or cable lateral raises instead")
    
    search_results = store.search_conversation("shoulder substitution")
    print(f"Search results for 'shoulder substitution': {len(search_results)} items found")
    for result in search_results:
        print(f"  - {result['role']}: {result['text'][:100]}...")
    
    # Test 4: Sticky context
    print("\n🎯 Test 4: Sticky context")
    store.save_query_context("last_logs_query", {"date": "2025-08-15", "day": "thursday"})
    store.save_query_context("last_plan_slice", {"day": "thursday"})
    
    context = store.get_last_query_context()
    print(f"Sticky context: {context}")
    
    print("\n✅ All memory layer tests completed!")
    
    # Test 5: AI Integration
    print("\n🤖 Test 5: AI Integration Test")
    try:
        # Test follow-up without parameters (should use sticky context)
        result = ai_service.get_ai_response("how does that compare to my plan?")
        print(f"AI follow-up response: {result['response'][:200]}...")
        print(f"Tools used: {result.get('tools_used', [])}")
    except Exception as e:
        print(f"AI integration test failed: {e}")

if __name__ == "__main__":
    test_conversation_memory()
