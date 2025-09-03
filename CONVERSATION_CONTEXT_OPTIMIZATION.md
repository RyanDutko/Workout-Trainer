# Conversation Context Optimization

## Changes Made

✅ **Removed recent conversation context from system prompt** in `ai_service_v2.py` to reduce token usage.

### What was removed:
- `recent_context = self.conversation_store.get_recent_window(max_turns=6)`
- `system_content += f"\n\n{recent_context}"`

### Impact:
- **Significantly reduced token usage** for simple queries like "hello"
- **Faster response times** due to smaller prompts
- **Lower API costs** for basic interactions

## Suggestions for More Efficient Conversation Context

### 1. **Smart Context Selection** (Recommended)
Instead of always including recent context, only include it when needed:

```python
def should_include_context(message: str) -> bool:
    """Only include context for follow-up questions"""
    follow_up_indicators = [
        'it', 'that', 'this', 'them', 'those', 'the', 'previous',
        'last', 'before', 'earlier', 'mentioned', 'said'
    ]
    return any(indicator in message.lower() for indicator in follow_up_indicators)
```

### 2. **Context Summarization**
Instead of raw conversation history, use AI to summarize recent context:

```python
def get_context_summary(self, max_turns: int = 3) -> str:
    """Get AI-summarized context instead of raw conversation"""
    recent_turns = self.conversation_store.get_recent_window(max_turns)
    if not recent_turns:
        return ""
    
    # Use a lightweight model to summarize
    summary_prompt = f"Summarize this conversation context in 1-2 sentences: {recent_turns}"
    # Call lightweight summarization model
    return summary
```

### 3. **Intent-Based Context**
Only include context relevant to the current query:

```python
def get_relevant_context(self, message: str, intent: str) -> str:
    """Get context only relevant to current query"""
    if intent == 'plan_modification':
        return self.get_plan_context()
    elif intent == 'workout_logging':
        return self.get_recent_workout_context()
    else:
        return ""  # No context for general questions
```

### 4. **Context Compression**
Use embeddings to find only semantically relevant context:

```python
def get_semantic_context(self, message: str, max_tokens: int = 200) -> str:
    """Get context based on semantic similarity to current message"""
    # Use embeddings to find relevant conversation snippets
    # Return only the most relevant context within token limit
```

### 5. **Hybrid Approach** (Best of both worlds)
Combine multiple strategies:

```python
def get_smart_context(self, message: str) -> str:
    # 1. Check if context is needed
    if not self.should_include_context(message):
        return ""
    
    # 2. Get intent
    intent = self.analyze_intent(message)
    
    # 3. Get relevant context based on intent
    if intent == 'follow_up':
        return self.get_context_summary(max_turns=2)
    elif intent == 'plan_related':
        return self.get_plan_context()
    else:
        return ""
```

## Current Status

- ✅ **Recent context disabled** - Token usage significantly reduced
- ✅ **App still functional** - All core features work without context
- ✅ **Ready for optimization** - Can implement smart context when needed

## Next Steps

1. **Monitor performance** - See how the app performs without context
2. **Identify pain points** - Note where context would be helpful
3. **Implement smart context** - Choose one of the above approaches based on needs
4. **A/B test** - Compare performance with and without smart context

## Benefits of Current Change

- **Reduced costs** - Fewer tokens per request
- **Faster responses** - Smaller prompts process faster
- **Better UX** - No unnecessary context for simple queries
- **Cleaner logs** - Easier to debug without massive system prompts
