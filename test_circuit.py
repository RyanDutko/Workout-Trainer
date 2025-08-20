
import requests
import json

def test_circuit():
    # Test data for Bicep Finisher Rounds
    circuit_data = {
        'day': 'thursday',
        'label': 'Bicep Finisher Rounds',
        'rounds': 2,
        'rest_between_rounds_sec': 90,
        'members': [
            {'exercise': 'DB Bicep Curl', 'reps': 10, 'weight': 20, 'tempo': 'slow'},
            {'exercise': 'DB Bicep Curl', 'reps': 15, 'weight': 15, 'tempo': 'fast'},
            {'exercise': 'DB Hammer Curl', 'reps': 10, 'weight': 15, 'tempo': 'slow'}
        ]
    }
    
    # Add circuit to plan
    response = requests.post('http://localhost:5000/add_circuit_to_plan', 
                           json=circuit_data)
    print(f"Add circuit response: {response.json()}")

if __name__ == "__main__":
    test_circuit()
