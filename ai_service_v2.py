import os
import json
from typing import Dict, List, Any, Optional
from openai import OpenAI
from models import Database, User, TrainingPlan, Workout
from datetime import datetime, timedelta

class AIServiceV2:
    def __init__(self, db: Database):
        self.db = db
        self.client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        self.user = User(db)
        self.training_plan = TrainingPlan(db)
        self.workout = Workout(db)

        # Define the tools/functions that the AI can call
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "compare_workout_to_plan",
                    "description": "Use to answer any question that compares actual performance to planned workouts (followed the plan, vs/versus, compliance, differences). Returns plan + actual + diff.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "date": {
                                "type": "string",
                                "description": "Calendar date in YYYY-MM-DD format"
                            },
                            "day": {
                                "type": "string",
                                "description": "Day of week (optional) - monday, tuesday, wednesday, thursday, friday, saturday, sunday"
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_logs_by_day_or_date",
                    "description": "Retrieve actual logged workouts for a specific calendar date or most recent matching weekday.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "day": {
                                "type": "string",
                                "description": "Day of week (optional) - monday, tuesday, wednesday, thursday, friday, saturday, sunday"
                            },
                            "date": {
                                "type": "string",
                                "description": "Calendar date in YYYY-MM-DD format (optional)"
                            },
                            "limit": {
                                "type": "integer",
                                "default": 100,
                                "description": "Maximum number of workouts to return"
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_weekly_plan",
                    "description": "Retrieve planned exercises; pass day to get a slice or omit for full plan.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "day": {
                                "type": "string",
                                "description": "Day of week (optional) - monday, tuesday, wednesday, thursday, friday, saturday, sunday"
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_user_profile",
                    "description": "User goal/level and latest plan philosophy (newest first).",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            }
        ]

    def get_ai_response(self, message: str, conversation_history: List[Dict] = None) -> Dict[str, Any]:
        """Get AI response using function calling with guardrails"""
        MAX_TOOL_CALLS = 5

        try:
            # Build conversation messages
            messages = [
                {
                    "role": "system", 
                    "content": """You are a coaching assistant inside a fitness app.
Ground all factual answers in tool results. 
For history/plan/comparison questions, call the appropriate tool(s) first.
If tools return no data, say so plainly. Do not invent.
When the user suggests a goal change, propose an update (JSON), do not write.
Prefer concise, actionable answers citing dates and exact numbers."""
                }
            ]

            # Add conversation history if provided
            if conversation_history:
                for conv in conversation_history[-3:]:  # Last 3 exchanges for context
                    messages.append({"role": "user", "content": conv['user_message']})
                    messages.append({"role": "assistant", "content": conv['ai_response']})

            # Add current message
            messages.append({"role": "user", "content": message})

            # Planner loop with guardrails
            seen = set()  # (tool_name, json.dumps(sorted(args.items())))
            tool_results_for_response = []

            for i in range(MAX_TOOL_CALLS):
                response = self.client.chat.completions.create(
                    model="gpt-4",
                    messages=messages,
                    tools=self.tools,
                    tool_choice="auto",
                    temperature=0.7,
                    max_tokens=1000
                )

                response_message = response.choices[0].message
                tool_calls = response_message.tool_calls

                if tool_calls:
                    print(f"🎯 User query: '{message}'")
                    print(f"🤖 AI planned {len(tool_calls)} tool calls: {[tc.function.name for tc in tool_calls]}")

                    # Add the AI's response with tool calls to the conversation
                    messages.append(response_message)

                    # Execute each tool call
                    for tool_call in tool_calls:
                        function_name = tool_call.function.name
                        function_args = json.loads(tool_call.function.arguments)

                        # Create stable key for duplicate detection
                        stable_args_key = json.dumps(sorted(function_args.items()))
                        key = (function_name, stable_args_key)

                        # Check for duplicate consecutive calls
                        if key in seen:
                            print(f"⚠️ BLOCKED duplicate tool call: {function_name} with same args")
                            messages.append({
                                "role": "assistant",
                                "content": "Tool already called with same arguments; please proceed to answer."
                            })
                            continue

                        seen.add(key)
                        print(f"🔧 AI is calling tool: {function_name} with args: {function_args}")

                        # Execute the function
                        tool_result = self._execute_tool(function_name, function_args)
                        tool_results_for_response.append(tool_result)

                        # Add tool result to conversation
                        messages.append({
                            "tool_call_id": tool_call.id,
                            "role": "tool",
                            "name": function_name,
                            "content": json.dumps(tool_result)
                        })

                    continue  # Continue the loop to get final response
                else:
                    # No more tools needed, return final response
                    return {
                        'response': response_message.content,
                        'tools_used': [name for name, _ in seen],
                        'tool_results': tool_results_for_response,
                        'success': True
                    }

            # Safety fallback if we hit max tool calls
            return {
                'response': "I tried multiple times to gather data. Here's what I have so far... Please ask a more specific question if you need additional details.",
                'tools_used': [name for name, _ in seen],
                'tool_results': tool_results_for_response,
                'success': True,
                'warning': 'Hit max tool call limit'
            }

        except Exception as e:
            print(f"⚠️ AI Service V2 error: {str(e)}")
            return {
                'response': f"I'm having trouble processing that right now. Please try again. Error: {str(e)}",
                'tools_used': [],
                'tool_results': [],
                'success': False,
                'error': str(e)
            }

    def _execute_tool(self, function_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool function and return the result"""
        try:
            if function_name == "compare_workout_to_plan":
                return self._compare_workout_to_plan(
                    date=args.get('date'),
                    day=args.get('day')
                )

            elif function_name == "get_logs_by_day_or_date":
                return self._get_logs_by_day_or_date(
                    day=args.get('day'),
                    date=args.get('date'),
                    limit=args.get('limit', 100)
                )

            elif function_name == "get_weekly_plan":
                return self._get_weekly_plan(args.get('day'))

            elif function_name == "get_user_profile":
                return self._get_user_profile()

            else:
                return {"error": f"Unknown function: {function_name}"}

        except Exception as e:
            return {"error": f"Tool execution failed: {str(e)}"}

    def _compare_workout_to_plan(self, date: str = None, day: str = None) -> Dict[str, Any]:
        """Composite tool to compare actual performance to planned workouts"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        # Determine the target date and day
        target_date = date
        target_day = day

        if date:
            # Convert date to day of week
            try:
                date_obj = datetime.strptime(date, '%Y-%m-%d')
                target_day = date_obj.strftime('%A').lower()
            except:
                pass
        elif day:
            # Find most recent matching day
            cursor.execute('''
                SELECT date_logged FROM workouts 
                WHERE strftime('%w', date_logged) = ? 
                ORDER BY date_logged DESC LIMIT 1
            ''', (str(['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'].index(day.lower())),))
            result = cursor.fetchone()
            if result:
                target_date = result[0]

        # Get planned exercises
        plan = []
        if target_day:
            cursor.execute('''
                SELECT exercise_name, target_sets, target_reps, target_weight, exercise_order
                FROM weekly_plan
                WHERE day_of_week = ?
                ORDER BY exercise_order
            ''', (target_day,))

            for row in cursor.fetchall():
                plan.append({
                    'exercise': row[0],
                    'sets': row[1],
                    'reps': row[2],
                    'weight': row[3],
                    'order': row[4]
                })

        # Get actual workouts
        actual = []
        if target_date:
            cursor.execute('''
                SELECT exercise_name, sets, reps, weight, notes
                FROM workouts
                WHERE date_logged = ?
                ORDER BY id
            ''', (target_date,))

            for row in cursor.fetchall():
                actual.append({
                    'exercise': row[0],
                    'sets': row[1],
                    'reps': row[2],
                    'weight': row[3],
                    'notes': row[4] or ''
                })

        # Calculate diff
        diff = []
        plan_exercises = {ex['exercise'].lower(): ex for ex in plan}
        actual_exercises = {ex['exercise'].lower(): ex for ex in actual}

        # Check planned exercises
        for planned in plan:
            ex_name = planned['exercise'].lower()
            if ex_name in actual_exercises:
                actual_ex = actual_exercises[ex_name]
                if (str(planned['sets']) == str(actual_ex['sets']) and 
                    planned['reps'] == actual_ex['reps'] and 
                    planned['weight'] == actual_ex['weight']):
                    diff.append({
                        'exercise': planned['exercise'],
                        'status': 'matched',
                        'details': 'Exactly as planned'
                    })
                else:
                    diff.append({
                        'exercise': planned['exercise'],
                        'status': 'modified',
                        'details': f"Plan: {planned['sets']}x{planned['reps']}@{planned['weight']}, Actual: {actual_ex['sets']}x{actual_ex['reps']}@{actual_ex['weight']}"
                    })
            else:
                diff.append({
                    'exercise': planned['exercise'],
                    'status': 'missing',
                    'details': 'Not performed'
                })

        # Check for extra exercises
        for actual_ex in actual:
            if actual_ex['exercise'].lower() not in plan_exercises:
                diff.append({
                    'exercise': actual_ex['exercise'],
                    'status': 'extra',
                    'details': f"Not in plan: {actual_ex['sets']}x{actual_ex['reps']}@{actual_ex['weight']}"
                })

        conn.close()

        return {
            "criteria": {"date": target_date, "day": target_day},
            "plan": plan,
            "actual": actual,
            "diff": diff
        }

    def _get_logs_by_day_or_date(self, day: str = None, date: str = None, limit: int = 100) -> Dict[str, Any]:
        """Get workout logs by day or date"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        if date:
            cursor.execute('''
                SELECT exercise_name, sets, reps, weight, notes, date_logged
                FROM workouts
                WHERE date_logged = ?
                ORDER BY id
                LIMIT ?
            ''', (date, limit))
        elif day:
            # Get most recent workouts for the specified day
            day_num = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'].index(day.lower())
            cursor.execute('''
                SELECT exercise_name, sets, reps, weight, notes, date_logged
                FROM workouts
                WHERE strftime('%w', date_logged) = ?
                ORDER BY date_logged DESC, id DESC
                LIMIT ?
            ''', (str(day_num), limit))
        else:
            cursor.execute('''
                SELECT exercise_name, sets, reps, weight, notes, date_logged
                FROM workouts
                ORDER BY date_logged DESC, id DESC
                LIMIT ?
            ''', (limit,))

        workouts = []
        for row in cursor.fetchall():
            workouts.append({
                'exercise': row[0],
                'sets': row[1],
                'reps': row[2],
                'weight': row[3],
                'notes': row[4] or '',
                'date': row[5]
            })

        conn.close()
        return {"workouts": workouts, "total_found": len(workouts)}

    def _get_weekly_plan(self, day: str = None) -> Dict[str, Any]:
        """Get weekly plan data"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        if day:
            cursor.execute('''
                SELECT day_of_week, exercise_name, target_sets, target_reps, target_weight, exercise_order, notes
                FROM weekly_plan
                WHERE day_of_week = ?
                ORDER BY exercise_order
            ''', (day,))
        else:
            cursor.execute('''
                SELECT day_of_week, exercise_name, target_sets, target_reps, target_weight, exercise_order, notes
                FROM weekly_plan
                ORDER BY 
                    CASE day_of_week
                        WHEN 'monday' THEN 1
                        WHEN 'tuesday' THEN 2
                        WHEN 'wednesday' THEN 3
                        WHEN 'thursday' THEN 4
                        WHEN 'friday' THEN 5
                        WHEN 'saturday' THEN 6
                        WHEN 'sunday' THEN 7
                    END, exercise_order
            ''')

        plan_data = []
        for row in cursor.fetchall():
            plan_data.append({
                'day': row[0],
                'exercise': row[1],
                'sets': row[2],
                'reps': row[3],
                'weight': row[4],
                'order': row[5],
                'notes': row[6] or ''
            })

        conn.close()
        return {"plan": plan_data, "total_exercises": len(plan_data)}

    def _get_user_profile(self) -> Dict[str, Any]:
        """Get user profile and latest plan philosophy"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        # Get user profile
        profile = self.user.get_profile()
        ai_prefs = self.user.get_ai_preferences()

        # Get latest plan philosophy
        cursor.execute('''
            SELECT plan_philosophy, progression_strategy, weekly_structure, special_considerations
            FROM plan_context
            WHERE user_id = 1
            ORDER BY created_date DESC
            LIMIT 1
        ''')

        philosophy = {}
        result = cursor.fetchone()
        if result:
            philosophy = {
                "core_philosophy": result[0] or '',
                "current_priorities": result[1] or '',
                "weekly_structure": result[2] or '',
                "special_considerations": result[3] or ''
            }

        conn.close()

        return {
            "profile": profile,
            "ai_preferences": ai_prefs,
            "philosophy": philosophy
        }