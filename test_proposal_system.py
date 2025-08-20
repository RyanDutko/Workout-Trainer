
#!/usr/bin/env python3

import sys
import os
sys.path.append('.')

from ai_service_v2 import AIServiceV2
from models import Database

def test_circuit_proposal():
    """Test the proposal/commit flow with a circuit"""
    print("🧪 Testing Circuit Proposal System")
    print("=" * 50)
    
    # Initialize services
    db = Database()
    ai_service = AIServiceV2(db)
    
    # Test 1: Propose a circuit
    print("\n1. Testing propose_plan_update...")
    
    circuit_block = {
        "block_type": "circuit",
        "label": "Bicep Finisher Rounds",
        "order_index": 99,
        "meta_json": {"rounds": 2, "rest_between_rounds_sec": 90},
        "members": [
            {"exercise": "DB Bicep Curl", "reps": 10, "weight": "20lbs", "tempo": "slow"},
            {"exercise": "DB Bicep Curl", "reps": 15, "weight": "15lbs", "tempo": "fast"},
            {"exercise": "DB Hammer Curl", "reps": 10, "weight": "15lbs", "tempo": "slow"}
        ]
    }
    
    proposal_result = ai_service._propose_plan_update(
        day="thursday",
        action="add_block", 
        block=circuit_block
    )
    
    print(f"Proposal result: {proposal_result}")
    
    if not proposal_result.get('proposal_id'):
        print("❌ Proposal failed")
        return
    
    proposal_id = proposal_result['proposal_id']
    print(f"✅ Proposal created with ID: {proposal_id}")
    print(f"📄 Summary: {proposal_result['summary']}")
    
    # Test 2: Commit the proposal
    print("\n2. Testing commit_plan_update...")
    
    commit_result = ai_service._commit_plan_update(proposal_id)
    print(f"Commit result: {commit_result}")
    
    if commit_result.get('wrote'):
        print(f"✅ Successfully wrote block_id: {commit_result.get('block_id')}")
        
        # Test 3: Verify it's in the plan
        print("\n3. Verifying plan contains the circuit...")
        thursday_plan = ai_service._get_weekly_plan("thursday")
        print(f"Thursday plan has {len(thursday_plan)} items")
        
        circuit_found = False
        for item in thursday_plan:
            if isinstance(item, dict) and item.get('block_type') == 'circuit':
                print(f"🔍 Found circuit: {item.get('label', 'Unnamed')}")
                circuit_found = True
                break
        
        if circuit_found:
            print("✅ Circuit successfully added and verified!")
        else:
            print("❌ Circuit not found in plan")
    else:
        print(f"❌ Commit failed: {commit_result}")

if __name__ == "__main__":
    test_circuit_proposal()
