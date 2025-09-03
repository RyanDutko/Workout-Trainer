# Token Optimization Implementation Plan

## Phase 1: Stable ID System

### 1.1 Database Schema Updates
```sql
-- Add stable IDs to weekly_plan
ALTER TABLE weekly_plan ADD COLUMN stable_id TEXT;
ALTER TABLE weekly_plan ADD COLUMN plan_hash TEXT;

-- Add stable IDs to workout_blocks (for circuits)
ALTER TABLE workout_blocks ADD COLUMN stable_id TEXT;

-- Create plan versioning table
CREATE TABLE plan_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_hash TEXT NOT NULL,
    version_timestamp TEXT,
    changes_json TEXT,
    user_id INTEGER DEFAULT 1
);
```

### 1.2 ID Generation Strategy
- **Day IDs**: `day_1`, `day_2`, etc. (Monday=1, Tuesday=2, etc.)
- **Block IDs**: `b_42`, `b_43`, etc. (unique across all days)
- **Member IDs**: `m_101`, `m_102`, etc. (for circuit members)
- **Plan Hash**: SHA256 of current plan state

### 1.3 Migration Script
```python
def migrate_to_stable_ids():
    """Migrate existing plan to stable IDs"""
    # Generate stable IDs for existing exercises
    # Create initial plan hash
    # Update all references
```

## Phase 2: Delta-Based Context System

### 2.1 Context Delta Tracking
```python
class ContextDelta:
    def __init__(self):
        self.changed_blocks = []  # Only blocks that changed
        self.removed_blocks = []  # Blocks that were removed
        self.added_blocks = []    # New blocks
        self.last_plan_hash = None
        self.current_plan_hash = None
    
    def get_context_snippet(self):
        """Return only changed parts of plan"""
        if not self.changed_blocks:
            return "Plan unchanged since last interaction"
        
        return f"Changes: {self.format_changes()}"
```

### 2.2 Smart Context Builder
```python
def build_delta_context(last_interaction_time):
    """Build context with only changes since last interaction"""
    # Get plan hash from last interaction
    # Compare with current plan hash
    # Return only deltas + essential info
```

## Phase 3: Structured Tool Calls

### 3.1 New Tool Schema
```python
TOOLS = {
    "update_block": {
        "description": "Update a specific block in the plan",
        "parameters": {
            "block_id": "string",
            "op": "update_block",
            "set": {
                "sets": "integer",
                "reps": "string", 
                "weight": "string"
            }
        }
    },
    "add_block": {
        "description": "Add a new block to a day",
        "parameters": {
            "day_id": "string",
            "op": "add_block",
            "exercise": "string",
            "sets": "integer",
            "reps": "string",
            "weight": "string"
        }
    }
}
```

### 3.2 Example Optimized Prompts

**Before (Current):**
```
"Here's your complete weekly plan:
Monday: Bench Press 3x8-10@185lbs, Squats 4x8-12@225lbs...
Change my Monday bench press to 4 sets"
```

**After (Optimized):**
```
"Plan changes since last interaction: b_42 (Monday bench) → 4 sets
Update b_42 to 4 sets"
```

## Phase 4: Implementation Steps

### Step 1: Database Migration
1. Add stable_id columns
2. Generate IDs for existing data
3. Create plan versioning table
4. Add indexes for performance

### Step 2: Update AI Service
1. Modify `_get_weekly_plan()` to return deltas
2. Update tool definitions to use IDs
3. Add delta tracking logic

### Step 3: Update Context Builders
1. Modify `build_plan_context()` to use deltas
2. Add plan hash comparison
3. Implement change detection

### Step 4: Update Frontend
1. Display stable IDs in UI (optional)
2. Update plan modification tools
3. Add change tracking indicators

## Expected Token Savings

### Current Token Usage:
- Full plan context: ~800 tokens
- Tool calls with full data: ~200-500 tokens
- Total per interaction: ~1000-1300 tokens

### Optimized Token Usage:
- Delta context: ~50-100 tokens
- Structured tool calls: ~50-100 tokens
- Total per interaction: ~100-200 tokens

**Overall Reduction: 80-85%**

## Testing Strategy

### 1. A/B Testing
- Run parallel systems (current vs optimized)
- Compare token usage and accuracy
- Measure user experience impact

### 2. Token Usage Monitoring
- Track tokens per interaction type
- Monitor delta effectiveness
- Measure plan change frequency

### 3. Fallback Strategy
- Keep current system as backup
- Graceful degradation if deltas fail
- Automatic fallback to full context

## Implementation Timeline

**Week 1**: Database schema updates and migration
**Week 2**: Core delta system implementation
**Week 3**: AI service updates and testing
**Week 4**: Frontend integration and optimization
**Week 5**: Testing and refinement

## Risk Mitigation

### 1. Data Integrity
- Backup before migration
- Validate all ID references
- Test plan hash consistency

### 2. User Experience
- Maintain current functionality
- Add visual indicators for changes
- Provide fallback options

### 3. Performance
- Index stable_id columns
- Cache plan hashes
- Optimize delta calculations

