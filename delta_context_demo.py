#!/usr/bin/env python3
"""
Delta-Based Context System Demo
Shows how to implement the suggested token optimizations
"""

import hashlib
import json
from datetime import datetime
from typing import Dict, List, Optional

class PlanDelta:
    """Track changes to the workout plan"""
    
    def __init__(self):
        self.changed_blocks = []
        self.removed_blocks = []
        self.added_blocks = []
        self.last_plan_hash = None
        self.current_plan_hash = None
    
    def calculate_plan_hash(self, plan_data: List[Dict]) -> str:
        """Calculate SHA256 hash of current plan state"""
        plan_str = json.dumps(plan_data, sort_keys=True)
        return hashlib.sha256(plan_str.encode()).hexdigest()[:16]
    
    def detect_changes(self, old_plan: List[Dict], new_plan: List[Dict]) -> Dict:
        """Detect what changed between two plan states"""
        old_by_id = {block['stable_id']: block for block in old_plan if 'stable_id' in block}
        new_by_id = {block['stable_id']: block for block in new_plan if 'stable_id' in block}
        
        changes = {
            'changed': [],
            'removed': [],
            'added': []
        }
        
        # Find changed blocks
        for block_id, new_block in new_by_id.items():
            if block_id in old_by_id:
                old_block = old_by_id[block_id]
                if new_block != old_block:
                    changes['changed'].append({
                        'block_id': block_id,
                        'old': old_block,
                        'new': new_block
                    })
            else:
                changes['added'].append(new_block)
        
        # Find removed blocks
        for block_id in old_by_id:
            if block_id not in new_by_id:
                changes['removed'].append(old_by_id[block_id])
        
        return changes

class OptimizedContextBuilder:
    """Build context using deltas instead of full plan"""
    
    def __init__(self):
        self.delta_tracker = PlanDelta()
        self.last_interaction_time = None
    
    def build_delta_context(self, user_message: str, last_interaction_time: Optional[datetime] = None) -> str:
        """Build context with only changes since last interaction"""
        
        # Get current plan
        current_plan = self._get_current_plan()
        current_hash = self.delta_tracker.calculate_plan_hash(current_plan)
        
        # If no previous interaction or plan unchanged, return minimal context
        if not last_interaction_time or current_hash == self.delta_tracker.last_plan_hash:
            return self._build_minimal_context(user_message)
        
        # Get plan from last interaction
        last_plan = self._get_plan_at_time(last_interaction_time)
        changes = self.delta_tracker.detect_changes(last_plan, current_plan)
        
        # Build delta context
        context = self._build_delta_context(changes, user_message)
        
        # Update tracking
        self.delta_tracker.last_plan_hash = current_hash
        self.delta_tracker.current_plan_hash = current_hash
        
        return context
    
    def _build_minimal_context(self, user_message: str) -> str:
        """Build minimal context when no changes detected"""
        return f"""Current plan unchanged since last interaction.
User message: {user_message}"""
    
    def _build_delta_context(self, changes: Dict, user_message: str) -> str:
        """Build context showing only changes"""
        context_parts = []
        
        if changes['added']:
            added_summary = []
            for block in changes['added']:
                added_summary.append(f"{block['stable_id']}: {block['exercise_name']} {block['target_sets']}x{block['target_reps']}@{block['target_weight']}")
            context_parts.append(f"Added: {', '.join(added_summary)}")
        
        if changes['changed']:
            changed_summary = []
            for change in changes['changed']:
                old = change['old']
                new = change['new']
                changes_list = []
                
                if old['target_sets'] != new['target_sets']:
                    changes_list.append(f"sets: {old['target_sets']}→{new['target_sets']}")
                if old['target_reps'] != new['target_reps']:
                    changes_list.append(f"reps: {old['target_reps']}→{new['target_reps']}")
                if old['target_weight'] != new['target_weight']:
                    changes_list.append(f"weight: {old['target_weight']}→{new['target_weight']}")
                
                changed_summary.append(f"{change['block_id']}: {', '.join(changes_list)}")
            context_parts.append(f"Changed: {', '.join(changed_summary)}")
        
        if changes['removed']:
            removed_summary = [f"{block['stable_id']}: {block['exercise_name']}" for block in changes['removed']]
            context_parts.append(f"Removed: {', '.join(removed_summary)}")
        
        context = f"Plan changes since last interaction: {'; '.join(context_parts)}"
        context += f"\nUser message: {user_message}"
        
        return context
    
    def _get_current_plan(self) -> List[Dict]:
        """Get current plan from database (mock implementation)"""
        # This would query the actual database
        return [
            {'stable_id': 'b_42', 'exercise_name': 'Bench Press', 'target_sets': 4, 'target_reps': '8-10', 'target_weight': '185lbs'},
            {'stable_id': 'b_43', 'exercise_name': 'Squats', 'target_sets': 4, 'target_reps': '8-12', 'target_weight': '225lbs'},
            {'stable_id': 'b_44', 'exercise_name': 'Deadlifts', 'target_sets': 3, 'target_reps': '5-8', 'target_weight': '275lbs'}
        ]
    
    def _get_plan_at_time(self, timestamp: datetime) -> List[Dict]:
        """Get plan state at specific time (mock implementation)"""
        # This would query plan_versions table
        return [
            {'stable_id': 'b_42', 'exercise_name': 'Bench Press', 'target_sets': 3, 'target_reps': '8-10', 'target_weight': '185lbs'},
            {'stable_id': 'b_43', 'exercise_name': 'Squats', 'target_sets': 4, 'target_reps': '8-12', 'target_weight': '225lbs'},
            {'stable_id': 'b_44', 'exercise_name': 'Deadlifts', 'target_sets': 3, 'target_reps': '5-8', 'target_weight': '275lbs'}
        ]

class OptimizedTools:
    """Optimized tool definitions using stable IDs"""
    
    @staticmethod
    def get_tool_definitions() -> List[Dict]:
        """Get optimized tool definitions"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "update_block",
                    "description": "Update a specific block in the plan using its stable ID",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "block_id": {
                                "type": "string",
                                "description": "Stable ID of the block to update (e.g., 'b_42')"
                            },
                            "sets": {
                                "type": "integer",
                                "description": "Number of sets"
                            },
                            "reps": {
                                "type": "string",
                                "description": "Rep range (e.g., '8-10')"
                            },
                            "weight": {
                                "type": "string",
                                "description": "Weight (e.g., '185lbs')"
                            }
                        },
                        "required": ["block_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "add_block",
                    "description": "Add a new exercise block to a specific day",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "day_id": {
                                "type": "string",
                                "description": "Day ID (e.g., 'day_1' for Monday)"
                            },
                            "exercise_name": {
                                "type": "string",
                                "description": "Name of the exercise"
                            },
                            "sets": {
                                "type": "integer",
                                "description": "Number of sets"
                            },
                            "reps": {
                                "type": "string",
                                "description": "Rep range"
                            },
                            "weight": {
                                "type": "string",
                                "description": "Weight"
                            }
                        },
                        "required": ["day_id", "exercise_name"]
                    }
                }
            }
        ]

def demo_token_savings():
    """Demo the token savings from delta-based context"""
    
    # Current approach (full plan context)
    current_context = """Here's your complete weekly plan:
Monday: Bench Press 3x8-10@185lbs, Squats 4x8-12@225lbs, Deadlifts 3x5-8@275lbs
Tuesday: Overhead Press 4x8-10@135lbs, Pull-ups 3x8-12@bodyweight, Rows 4x10-12@155lbs
Wednesday: Incline Press 4x8-10@165lbs, Leg Press 4x12-15@315lbs, Bicep Curls 3x10-12@35lbs

User message: Change my Monday bench press to 4 sets"""
    
    # Optimized approach (delta context)
    optimized_context = """Plan changes since last interaction: b_42 (Bench Press) sets: 3→4
User message: Change my Monday bench press to 4 sets"""
    
    # Calculate token savings
    current_tokens = len(current_context) // 4  # Rough estimation
    optimized_tokens = len(optimized_context) // 4
    
    print("=== TOKEN SAVINGS DEMO ===")
    print(f"Current approach: {current_tokens} tokens")
    print(f"Optimized approach: {optimized_tokens} tokens")
    print(f"Token reduction: {((current_tokens - optimized_tokens) / current_tokens * 100):.1f}%")
    print(f"Savings: {current_tokens - optimized_tokens} tokens per interaction")
    
    print("\n=== CONTEXT COMPARISON ===")
    print("Current (Full Plan):")
    print(current_context)
    print("\nOptimized (Delta):")
    print(optimized_context)

def demo_structured_tools():
    """Demo structured tool calls using stable IDs"""
    
    print("\n=== STRUCTURED TOOL CALLS DEMO ===")
    
    # Current approach (natural language)
    current_tool_call = {
        "function": "modify_plan",
        "arguments": {
            "day": "monday",
            "exercise": "bench press",
            "sets": 4,
            "reps": "8-10",
            "weight": "185lbs"
        }
    }
    
    # Optimized approach (structured with IDs)
    optimized_tool_call = {
        "function": "update_block",
        "arguments": {
            "block_id": "b_42",
            "sets": 4
        }
    }
    
    print("Current tool call:")
    print(json.dumps(current_tool_call, indent=2))
    print(f"Tokens: ~{len(json.dumps(current_tool_call)) // 4}")
    
    print("\nOptimized tool call:")
    print(json.dumps(optimized_tool_call, indent=2))
    print(f"Tokens: ~{len(json.dumps(optimized_tool_call)) // 4}")

if __name__ == "__main__":
    demo_token_savings()
    demo_structured_tools()
    
    print("\n=== IMPLEMENTATION NEXT STEPS ===")
    print("1. Add stable_id columns to weekly_plan table")
    print("2. Create plan_versions table for change tracking")
    print("3. Update AI service to use delta context")
    print("4. Modify tool definitions to use stable IDs")
    print("5. Test with real user interactions")

