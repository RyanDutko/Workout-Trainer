import os
import json
import uuid
from typing import Dict, List, Any, Optional
from openai import OpenAI
from models import Database, User, TrainingPlan, Workout
from conversation_store import ConversationStore
from datetime import datetime, timedelta
import zoneinfo

# Detroit timezone for consistent date resolution
DETROIT_TZ = zoneinfo.ZoneInfo("America/Detroit")

def resolve_date_or_day(date_str: str = None, day_str: str = None) -> tuple[str, str]:
    """
    Returns (resolved_date_yyyy_mm_dd, normalized_day_lower) or (None, None) if unresolvable.
    Preference: explicit date_str if valid; else resolve day_str to most recent past weekday.
    """
    # 1) explicit date
    if date_str:
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
            return d.isoformat(), d.strftime("%A").lower()
        except ValueError:
            pass  # fall through to day logic

    # 2) resolve weekday
    if day_str:
        day_l = day_str.strip().lower()
        weekdays = ["sunday","monday","tuesday","wednesday","thursday","friday","saturday"]
        if day_l in weekdays:
            today = datetime.now(DETROIT_TZ).date()
            target_idx = weekdays.index(day_l)
            today_idx = int(datetime.now(DETROIT_TZ).strftime("%w"))  # 0=Sun..6=Sat
            delta = (today_idx - target_idx) % 7
            # use today if same weekday; otherwise go back to last occurrence
            resolved = today if delta == 0 else (today - timedelta(days=delta))
            return resolved.isoformat(), day_l

    return None, None

class AIServiceV2:
    def __init__(self, db: Database):
        self.db = db
        self.client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        self.user = User(db)
        self.training_plan = TrainingPlan(db)
        self.workout = Workout(db)
        self.conversation_store = ConversationStore(db.db_path)

        # Define the tools/functions that the AI can call
        # In-memory proposal storage for two-step write flow
        self.pending_proposals = {}

        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_workout_history",
                    "description": "Get workout history for a specific date or recent workouts. Use when user asks about past workouts.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "date": {
                                "type": "string",
                                "description": "Date in YYYY-MM-DD format (optional)"
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Number of recent workouts to return (default: 10)"
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_weekly_plan",
                    "description": "Returns normalized blocks (single/superset/circuit) for a day or full week; circuits include rounds + members.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "day": {
                                "type": "string",
                                "description": "Specific day to get plan for (optional): monday, tuesday, wednesday, thursday, friday, saturday, sunday"
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "propose_plan_update",
                    "description": "Propose changes to the weekly workout plan. Use this to add, modify, or remove workout blocks/exercises. When the user mentions 'rounds' (e.g., 2 rounds), include an integer rounds in the block.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "day": {
                                "type": "string",
                                "description": "Day to add block to: monday, tuesday, wednesday, thursday, friday, saturday, sunday"
                            },
                            "action": {
                                "type": "string",
                                "description": "Action to take: add_block, update_block, remove_block"
                            },
                            "block": {
                                "type": "object",
                                "description": "Block definition with block_type, label, meta_json, and members",
                                "properties": {
                                    "block_type": {
                                        "type": "string",
                                        "description": "Type: single, circuit, superset, rounds"
                                    },
                                    "label": {
                                        "type": "string",
                                        "description": "Display name for the block"
                                    },
                                    "order_index": {
                                        "type": "integer",
                                        "description": "Position in the day (optional, will auto-assign)"
                                    },
                                    "rounds": {
                                        "type": "integer",
                                        "description": "Number of rounds for circuit/rounds blocks", "default": 1
                                    },
                                    "meta_json": {
                                        "type": "object",
                                        "description": "Metadata like rounds, rest_between_rounds_sec"
                                    },
                                    "members": {
                                        "type": "array",
                                        "description": "Array of exercises with reps/weight/tempo",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "exercise": {"type": "string"},
                                                "reps": {"type": "integer"},
                                                "weight": {"type": "string"},
                                                "tempo": {"type": "string"}
                                            }
                                        }
                                    }
                                }
                            }
                        },
                        "required": ["day", "action", "block"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "commit_plan_update",
                    "description": "Persist the previously proposed plan update. Returns {status:'ok', block_id, wrote: true} on success.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "proposal_id": {
                                "type": "string",
                                "description": "The proposal_id returned from propose_plan_update"
                            }
                        },
                        "required": ["proposal_id"]
                    }
                }
            },
            {
                "type": "function", 
                "function": {
                    "name": "get_exercise_progression",
                    "description": "Get progression data for a specific exercise. Use when user asks about progress, improvement, or trends for an exercise.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "exercise_name": {
                                "type": "string",
                                "description": "Name of the exercise to get progression for"
                            },
                            "limit": {
                                "type": "integer", 
                                "description": "Number of recent records to return (default: 10)"
                            }
                        },
                        "required": ["exercise_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_session",
                    "description": "Get normalized workout session data for a specific date. Use when user asks about a specific workout session.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "date": {
                                "type": "string",
                                "description": "Date in YYYY-MM-DD format"
                            }
                        },
                        "required": ["date"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "compare_workout_to_plan",
                    "description": "Compares normalized plan (including circuits/rounds) vs. actual and returns a diff.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "date": {
                                "type": "string",
                                "description": "Date in YYYY-MM-DD format (optional)"
                            },
                            "day": {
                                "type": "string",
                                "description": "Day of week (optional): monday, tuesday, wednesday, thursday, friday, saturday, sunday"
                            }
                        }
                    }
                }
            }
        ]

    def get_ai_response(self, message: str, conversation_history: List[Dict] = None) -> Dict[str, Any]:
        """Get AI response using function calling with guardrails"""
        MAX_TOOL_CALLS = 5

        try:
            # Get current date and time for context
            current_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            current_year = datetime.now().year

            # Get recent conversation window
            recent_context = self.conversation_store.get_recent_window(max_turns=6)

            system_content = f"""You are a coaching assistant inside a fitness app.

CURRENT DATE/TIME: {current_datetime}
CURRENT YEAR: {current_year}

You have tools to fetch pinned facts, recent context, and older snippets. Use them when unsure; don't guess.

Ground all factual answers in tool results. 
For history/plan/comparison questions, call the appropriate tool(s) first.
If tools return no data, say so plainly. Do not invent.
Prefer concise, actionable answers citing dates and exact numbers."""

            if recent_context:
                system_content += f"\n\n{recent_context}"

            messages = [
                {
                    "role": "system", 
                    "content": system_content
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

                        print(f"✅ Tool result: {json.dumps(tool_result, indent=2)}")  # Debug output

                        # Add tool result to conversation
                        messages.append({
                            "tool_call_id": tool_call.id,
                            "role": "tool",
                            "name": function_name,
                            "content": json.dumps(tool_result)
                        })

                    continue  # Continue the loop to get final response
                else:
                    # Check for phantom writes before finalizing response
                    response_content = response_message.content.lower()
                    if any(phrase in response_content for phrase in ['added to', 'created', 'updated your plan', 'wrote']) and not any('commit_plan_update' in str(result) for result in tool_results_for_response):
                        # Phantom write detected - nudge the model to commit
                        messages.append({
                            "role": "system",
                            "content": "Reminder: you must call commit_plan_update to perform writes. Do not claim success before commit returns {status:'ok'}."
                        })
                        continue  # Go back to model for commit

                    # No more tools needed, save conversation turn and return final response
                    self.conversation_store.append_turn(message, response_message.content)

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

            elif function_name == "add_exercise_to_plan":
                return self._add_exercise_to_plan(
                    day=args.get('day'),
                    exercise_name=args.get('exercise_name'),
                    sets=args.get('sets', 3),
                    reps=args.get('reps', '8-12'),
                    weight=args.get('weight', 'bodyweight')
                )

            elif function_name == "add_circuit_to_plan":
                return self._add_circuit_to_plan(
                    day=args.get('day'),
                    label=args.get('label', 'Circuit'),
                    rounds=args.get('rounds', 2),
                    rest_between_rounds_sec=args.get('rest_between_rounds_sec', 90),
                    members=args.get('members')
                )

            elif function_name == "update_exercise_in_plan":
                return self._update_exercise_in_plan(
                    day=args.get('day'),
                    exercise_name=args.get('exercise_name'),
                    sets=args.get('sets'),
                    reps=args.get('reps'),
                    weight=args.get('weight')
                )

            elif function_name == "remove_exercise_from_plan":
                return self._remove_exercise_from_plan(
                    day=args.get('day'),
                    exercise_name=args.get('exercise_name')
                )

            elif function_name == "get_pinned_facts":
                return self._get_pinned_facts()

            elif function_name == "search_conversation":
                return self._search_conversation(
                    query=args.get('query'),
                    max_items=args.get('max_items', 3)
                )

            elif function_name == "get_last_query_context":
                return self._get_last_query_context()

            elif function_name == "get_session":
                return self.get_session(
                    date=args.get('date')
                )

            elif function_name == "get_workout_history":
                return self._get_workout_history(
                    date=args.get('date'),
                    limit=args.get('limit', 10)
                )

            elif function_name == "get_exercise_progression":
                return self._get_exercise_progression(
                    exercise_name=args.get('exercise_name'),
                    limit=args.get('limit', 10)
                )

            elif function_name == "propose_plan_update":
                return self._propose_plan_update(
                    day=args.get('day'),
                    action=args.get('action'),
                    block=args.get('block')
                )

            elif function_name == "commit_plan_update":
                return self._commit_plan_update(
                    proposal_id=args.get('proposal_id')
                )

            else:
                return {"error": f"Unknown function: {function_name}"}

        except Exception as e:
            return {"error": f"Tool execution failed: {str(e)}"}

    def _compare_workout_to_plan(self, date: str = None, day: str = None) -> Dict[str, Any]:
        """Composite tool to compare actual performance to planned workouts"""
        resolved_date, resolved_day = resolve_date_or_day(date, day)
        print(f"RESOLVE: date={resolved_date}, day={resolved_day}")

        # Auto-load from sticky context if parameters missing
        if not resolved_date and not resolved_day:
            try:
                context = self.conversation_store.get_last_query_context()

                # Try last comparison context first
                if "last_comparison" in context:
                    last_comp = context["last_comparison"]
                    resolved_date = last_comp.get("date")
                    resolved_day = last_comp.get("day")
                # Fall back to last logs query
                elif "last_logs_query" in context:
                    last_logs = context["last_logs_query"]
                    resolved_date = last_logs.get("date")
                    resolved_day = last_logs.get("day")

                if resolved_date or resolved_day:
                    print(f"CTX_LOAD for compare_workout_to_plan → date={resolved_date}, day={resolved_day}")

            except Exception as e:
                print(f"Failed to auto-load context: {e}")

        if not resolved_date and not resolved_day:
            return {"error": "missing_criteria", "hint": "provide date (YYYY-MM-DD) or day (e.g., 'tuesday')"}

        conn = self.db.get_connection()
        cursor = conn.cursor()

        target_date = resolved_date
        target_day = resolved_day

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

        print(f"TOOL_RESULT_LEN(compare_workout_to_plan) plan={len(plan)} actual={len(actual)} diff={len(diff)}")

        # Save sticky context for follow-ups
        if target_date or target_day:
            self.conversation_store.save_query_context("last_comparison", {
                "date": target_date,
                "day": target_day
            })

        return {
            "criteria": {"date": target_date, "day": target_day},
            "plan": plan,
            "actual": actual,
            "diff": diff
        }

    def _get_logs_by_day_or_date(self, day: str = None, date: str = None, limit: int = 100) -> Dict[str, Any]:
        """Get workout logs by day or date"""
        resolved_date, resolved_day = resolve_date_or_day(date, day)
        print(f"RESOLVE: date={resolved_date}, day={resolved_day}")

        if not resolved_date and not resolved_day:
            return {"error": "missing_criteria", "hint": "provide date (YYYY-MM-DD) or day (e.g., 'tuesday')"}

        conn = self.db.get_connection()
        cursor = conn.cursor()

        if resolved_date:
            # Use exact date
            cursor.execute('''
                SELECT exercise_name, sets, reps, weight, notes, date_logged
                FROM workouts
                WHERE date_logged = ?
                ORDER BY id ASC
                LIMIT ?
            ''', (resolved_date, limit))
        elif resolved_day:
            # Query by weekday pattern for historical data
            day_num = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'].index(resolved_day)
            cursor.execute('''
                SELECT exercise_name, sets, reps, weight, notes, date_logged
                FROM workouts
                WHERE strftime('%w', date_logged) = ?
                ORDER BY date_logged DESC, id ASC
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

        # Save sticky context for follow-ups
        if resolved_date or resolved_day:
            self.conversation_store.save_query_context("last_logs_query", {
                "date": resolved_date,
                "day": resolved_day
            })
            print(f"CTX_SAVE last_logs_query date={resolved_date}, day={resolved_day}")

        print(f"TOOL_RESULT_LEN(get_logs_by_day_or_date)={len(workouts)}")

        return {
            "criteria": {"date": resolved_date, "day": resolved_day},
            "workouts": workouts, 
            "total_found": len(workouts)
        }

    def _get_weekly_plan(self, day: str = None) -> Dict[str, Any]:
        """Get weekly workout plan, optionally filtered by day, including circuit blocks"""
        # Use the existing workout model to get plan data
        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            # Get plan data with circuit support
            cursor.execute('''
                SELECT day_of_week, exercise_name, target_sets, target_reps, target_weight, exercise_order,
                       COALESCE(block_type, 'single') as block_type, 
                       COALESCE(meta_json, '{}') as meta_json,
                       COALESCE(members_json, '[]') as members_json
                FROM weekly_plan
                ORDER BY day_of_week, exercise_order
            ''')

            all_plan = cursor.fetchall()
        except Exception as e:
            print(f"Error fetching weekly plan: {e}")
            all_plan = []
        finally:
            conn.close()

        if not all_plan:
            return [] if day else {}

        # Group by day with circuit support
        plan_by_day = {}
        for row in all_plan:
            day_name, exercise_name, sets, reps, weight, order, block_type, meta_json, members_json = row

            if day_name not in plan_by_day:
                plan_by_day[day_name] = []

            if block_type == 'circuit':
                # Parse circuit data
                try:
                    meta = json.loads(meta_json) if meta_json else {}
                    members = json.loads(members_json) if members_json else []
                    rounds = meta.get('rounds', 1)

                    circuit_sets = []
                    for round_idx in range(rounds):
                        for member_idx, member in enumerate(members):
                            circuit_sets.append({
                                'exercise': member.get('exercise', ''),
                                'block_type': 'circuit',
                                'member_idx': member_idx,
                                'set_idx': round_idx,
                                'reps': member.get('reps'),
                                'weight': member.get('weight'),
                                'tempo': member.get('tempo'),
                                'status': 'planned'
                            })

                    plan_by_day[day_name].append({
                        'block_type': 'circuit',
                        'label': exercise_name,
                        'order_index': order,
                        'meta': meta,
                        'members': members,
                        'sets': circuit_sets
                    })
                except json.JSONDecodeError:
                    # Fallback to simple format
                    plan_by_day[day_name].append({
                        'exercise': exercise_name,
                        'sets': sets,
                        'reps': reps,
                        'weight': weight,
                        'block_type': 'single',
                        'order': order
                    })
            else:
                # Standard exercise
                plan_by_day[day_name].append({
                    'exercise': exercise_name,
                    'sets': sets,
                    'reps': reps,
                    'weight': weight,
                    'block_type': 'single',
                    'order': order
                })

        if day:
            result = plan_by_day.get(day.lower(), [])
            print(f"TOOL_RESULT_LEN(get_weekly_plan[{day}])={len(result)}")
            return result
        else:
            total_exercises = sum(len(exercises) for exercises in plan_by_day.values())
            print(f"TOOL_RESULT_LEN(get_weekly_plan)={total_exercises}")
            return plan_by_day

    def get_session(self, date):
        """Get normalized workout session data for a specific date"""
        import sys
        sys.path.append('.')
        from app import normalize_session

        result = normalize_session(date)
        print(f"TOOL_RESULT_LEN(get_session)={len(result)}")
        return result

    def compare_workout_to_plan(self, date=None, day=None):
        """Compare actual workout to planned workout"""
        import sys
        from datetime import datetime
        sys.path.append('.')
        from app import normalize_session

        # Resolve date and day
        if not date and not day:
            date = datetime.now().strftime('%Y-%m-%d')
            day = datetime.now().strftime('%A').lower()
        elif date and not day:
            date_obj = datetime.strptime(date, '%Y-%m-%d')
            day = date_obj.strftime('%A').lower()
        elif day and not date:
            # Find most recent date for this day
            date = datetime.now().strftime('%Y-%m-%d')  # Simplified for now

        # Get actual workout
        actual = normalize_session(date)

        # Get planned workout for this day
        plan_data = self._get_weekly_plan(day)

        # Flatten plan data to comparable format
        plan = []
        for item in plan_data:
            if item.get('block_type') == 'circuit' and 'sets' in item:
                plan.extend(item['sets'])
            else:
                plan.append({
                    'exercise': item.get('exercise', ''),
                    'block_type': item.get('block_type', 'single'),
                    'member_idx': None,
                    'set_idx': 0,
                    'reps': item.get('reps'),
                    'weight': item.get('weight'),
                    'status': 'planned'
                })

        # Create diff
        diff = []
        actual_exercises = {(row['exercise'], row.get('member_idx', 0), row.get('set_idx', 0)): row for row in actual}
        plan_exercises = {(row['exercise'], row.get('member_idx', 0), row.get('set_idx', 0)): row for row in plan}

        # Find matches and modifications
        for key, plan_row in plan_exercises.items():
            if key in actual_exercises:
                actual_row = actual_exercises[key]
                if (actual_row.get('reps') != plan_row.get('reps') or 
                    actual_row.get('weight') != plan_row.get('weight')):
                    diff.append({
                        'type': 'modified',
                        'exercise': plan_row['exercise'],
                        'planned': plan_row,
                        'actual': actual_row
                    })
                else:
                    diff.append({
                        'type': 'matched',
                        'exercise': plan_row['exercise']
                    })
            else:
                diff.append({
                    'type': 'missing',
                    'exercise': plan_row['exercise'],
                    'planned': plan_row
                })

        # Find extra exercises
        for key, actual_row in actual_exercises.items():
            if key not in plan_exercises:
                diff.append({
                    'type': 'extra',
                    'exercise': actual_row['exercise'],
                    'actual': actual_row
                })

        result = {
            'criteria': {'date': date, 'day': day},
            'plan': plan,
            'actual': actual,
            'diff': diff
        }

        print(f"TOOL_RESULT_LEN(compare_workout_to_plan) plan={len(plan)} actual={len(actual)} diff={len(diff)}")
        return result

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

    def _add_exercise_to_plan(self, day: str, exercise_name: str, sets: int = 3, reps: str = "8-12", weight: str = "bodyweight") -> Dict[str, Any]:
        """Add a new exercise to the weekly plan"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            # Get next order for the day
            cursor.execute('SELECT COALESCE(MAX(exercise_order), 0) + 1 FROM weekly_plan WHERE day_of_week = ?', (day.lower(),))
            next_order = cursor.fetchone()[0]

            # Insert the new exercise
            cursor.execute('''
                INSERT INTO weekly_plan
                (day_of_week, exercise_name, target_sets, target_reps, target_weight, exercise_order, created_by, newly_added, date_added)
                VALUES (?, ?, ?, ?, ?, ?, 'ai_v2', TRUE, ?)
            ''', (day.lower(), exercise_name, sets, reps, weight, next_order, datetime.now().strftime('%Y-%m-%d')))

            conn.commit()
            conn.close()

            return {
                "success": True,
                "message": f"Added {exercise_name} to {day.title()}: {sets}x{reps}@{weight}",
                "exercise_added": {
                    "day": day.lower(),
                    "exercise": exercise_name,
                    "sets": sets,
                    "reps": reps,
                    "weight": weight,
                    "order": next_order
                }
            }

        except Exception as e:
            conn.close()
            return {"success": False, "error": f"Failed to add exercise: {str(e)}"}

    def _update_exercise_in_plan(self, day: str, exercise_name: str, sets: int = None, reps: str = None, weight: str = None) -> Dict[str, Any]:
        """Update an existing exercise in the weekly plan"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            # Build update query dynamically based on provided parameters
            update_fields = []
            update_values = []

            if sets is not None:
                update_fields.append("target_sets = ?")
                update_values.append(sets)
            if reps is not None:
                update_fields.append("target_reps = ?")
                update_values.append(reps)
            if weight is not None:
                update_fields.append("target_weight = ?")
                update_values.append(weight)

            if not update_fields:
                return {"success": False, "error": "No fields to update"}

            update_values.extend([day.lower(), exercise_name])

            cursor.execute(f'''
                UPDATE weekly_plan
                SET {', '.join(update_fields)}
                WHERE day_of_week = ? AND LOWER(exercise_name) = LOWER(?)
            ''', update_values)

            if cursor.rowcount > 0:
                conn.commit()
                conn.close()
                return {
                    "success": True,
                    "message": f"Updated {exercise_name} on {day.title()}",
                    "exercise_updated": {
                        "day": day.lower(),
                        "exercise": exercise_name,
                        "sets": sets,
                        "reps": reps,
                        "weight": weight
                    }
                }
            else:
                conn.close()
                return {"success": False, "error": f"Exercise '{exercise_name}' not found on {day.title()}"}

        except Exception as e:
            conn.close()
            return {"success": False, "error": f"Failed to update exercise: {str(e)}"}

    def _remove_exercise_from_plan(self, day: str, exercise_name: str) -> Dict[str, Any]:
        """Remove an exercise from the weekly plan"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            # Check if exercise exists first
            cursor.execute('''
                SELECT exercise_name FROM weekly_plan
                WHERE day_of_week = ? AND LOWER(exercise_name) = LOWER(?)
            ''', (day.lower(), exercise_name))

            if not cursor.fetchone():
                conn.close()
                return {"success": False, "error": f"Exercise '{exercise_name}' not found on {day.title()}"}

            # Remove the exercise
            cursor.execute('''
                DELETE FROM weekly_plan
                WHERE day_of_week = ? AND LOWER(exercise_name) = LOWER(?)
            ''', (day.lower(), exercise_name))

            conn.commit()
            conn.close()

            return {
                "success": True,
                "message": f"Removed {exercise_name} from {day.title()}",
                "exercise_removed": {
                    "day": day.lower(),
                    "exercise": exercise_name
                }
            }

        except Exception as e:
            conn.close()
            return {"success": False, "error": f"Failed to remove exercise: {str(e)}"}

    def _get_pinned_facts(self) -> Dict[str, Any]:
        """Get pinned user facts"""
        try:
            facts = self.conversation_store.get_pinned_facts()
            return {"facts": facts, "total_facts": len(facts)}
        except Exception as e:
            return {"error": f"Failed to get pinned facts: {str(e)}"}

    def _search_conversation(self, query: str, max_items: int = 3) -> Dict[str, Any]:
        """Search conversation history for relevant snippets"""
        try:
            results = self.conversation_store.search_conversation(query, max_items)
            return {"results": results, "query": query, "total_found": len(results)}
        except Exception as e:
            return {"error": f"Failed to search conversation: {str(e)}"}

    def _get_last_query_context(self) -> Dict[str, Any]:
        """Get last query context for follow-ups"""
        try:
            context = self.conversation_store.get_last_query_context()
            return {"context": context}
        except Exception as e:
            return {"error": f"Failed to get last query context: {str(e)}"}

    def _add_circuit_to_plan(self, day: str, label: str = 'Circuit', rounds: int = 2, rest_between_rounds_sec: int = 90, members: list = None) -> Dict[str, Any]:
        """Add a circuit block to the weekly plan"""
        if not members:
            return {"success": False, "error": "Circuit members are required"}

        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            import json
            from datetime import datetime

            # Get next order for the day
            cursor.execute('SELECT COALESCE(MAX(exercise_order), 0) + 1 FROM weekly_plan WHERE day_of_week = ?', (day.lower(),))
            next_order = cursor.fetchone()[0]

            # Create meta data for the circuit
            meta_data = {
                'rounds': rounds,
                'rest_between_rounds_sec': rest_between_rounds_sec
            }

            # Insert circuit into weekly plan
            cursor.execute('''
                INSERT INTO weekly_plan
                (day_of_week, exercise_name, target_sets, target_reps, target_weight, exercise_order,
                 block_type, meta_json, members_json, created_by, newly_added, date_added)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (day.lower(), label, rounds, f'{len(members)} exercises', 'circuit', next_order,
                  'circuit', json.dumps(meta_data), json.dumps(members), 'ai_v2', True, datetime.now().strftime('%Y-%m-%d')))

            conn.commit()
            conn.close()

            return {
                'success': True,
                'message': f'Added {label} circuit to {day.title()}',
                'circuit': {
                    'day': day.lower(),
                    'label': label,
                    'rounds': rounds,
                    'members': members,
                    'order': next_order
                }
            }

        except Exception as e:
            conn.close()
            return {'success': False, 'error': f'Failed to add circuit: {str(e)}'}

    def _get_workout_history(self, date: str = None, limit: int = 10) -> Dict[str, Any]:
        """Get workout history for a specific date or recent workouts"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            if date:
                cursor.execute('''
                    SELECT exercise_name, sets, reps, weight, notes, date_logged
                    FROM workouts
                    WHERE date_logged = ?
                    ORDER BY id
                ''', (date,))
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
            return {'workouts': workouts, 'total_found': len(workouts)}

        except Exception as e:
            conn.close()
            return {'error': f'Failed to get workout history: {str(e)}'}

    def _get_exercise_progression(self, exercise_name: str, limit: int = 10) -> Dict[str, Any]:
        """Get progression data for a specific exercise"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                SELECT date_logged, sets, reps, weight, notes
                FROM workouts
                WHERE LOWER(exercise_name) LIKE LOWER(?)
                ORDER BY date_logged DESC
                LIMIT ?
            ''', (f'%{exercise_name}%', limit))

            progression = []
            for row in cursor.fetchall():
                progression.append({
                    'date': row[0],
                    'sets': row[1],
                    'reps': row[2],
                    'weight': row[3],
                    'notes': row[4] or ''
                })

            conn.close()
            return {
                'exercise_name': exercise_name,
                'progression': progression,
                'total_found': len(progression)
            }

        except Exception as e:
            conn.close()
            return {'error': f'Failed to get exercise progression: {str(e)}'}

    def _propose_plan_update(self, day: str, action: str, block: dict) -> Dict[str, Any]:
        """Validate and normalize a plan update, return proposal_id for commit"""
        import uuid

        try:
            # Generate unique proposal ID
            proposal_id = f"pr_{uuid.uuid4().hex[:8]}"

            # Extract block details
            block_type = (block.get("block_type") or "single").lower()
            if block_type == "complex":
                block_type = "circuit"
            
            label = block.get("label", f"New {block_type.title()} Block")
            order_index = block.get("order_index", 99)
            members = block.get("members", [])
            rounds = int(block.get("rounds") or 1)

            # Normalize the block structure
            normalized_block = {
                "block_type": block_type,
                "label": label,
                "order_index": order_index,
                "rounds": rounds,
                "meta_json": (block.get("meta_json") or block.get("meta") or {}),
                "members": members,
                "sets": []
            }

            # Create planned sets for circuit/rounds blocks
            if block_type in ("circuit", "rounds"):
                for r in range(rounds):
                    for mi, m in enumerate(members):
                        normalized_block["sets"].append({
                            **m,
                            "block_type": block_type,
                            "member_idx": mi,
                            "set_idx": r,        # 0-based
                            "round_index": r+1,  # 1-based for UI
                            "status": "planned"
                        })


            # Validate required fields
            if not day or day.lower() not in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']:
                return {'error': 'Invalid day specified'}

            if not action or action not in ['add_block', 'update_block', 'remove_block']:
                return {'error': 'Invalid action specified'}

            # Store the proposal
            self.pending_proposals[proposal_id] = {
                'day': day.lower(),
                'action': action,
                'block': normalized_block,
                'timestamp': datetime.now().isoformat()
            }

            # Generate user-friendly summary based on action
            block_type = normalized_block['block_type']
            label = normalized_block['label']

            if action == "add_block":
                if block_type == 'circuit':
                    rounds = normalized_block['rounds']
                    members_count = len(normalized_block['members'])
                    summary = f"Add '{label}' (circuit, {rounds} rounds, {members_count} members) to {day.title()}"
                else:
                    summary = f"Add '{label}' ({block_type}) to {day.title()}"
            elif action == "remove_block":
                summary = f"Remove block titled '{label}' from {day.title()}"
            else:
                summary = f"{action} '{label}' on {day.title()}"

            print(f"PROPOSE id={proposal_id} day={day} action={action} type={block_type} rounds={normalized_block['rounds']} members={len(normalized_block['members'])}")

            proposal_payload = {
                'proposal_id': proposal_id,
                'summary': summary,
                'normalized_block': normalized_block,
                'action': action,
                'day': day.lower()
            }

            # Add target_label for remove operations
            if action == "remove_block":
                proposal_payload['target_label'] = label

            return proposal_payload

        except Exception as e:
            return {'error': f'Failed to create proposal: {str(e)}'}

    def _commit_plan_update(self, proposal_id: str) -> Dict[str, Any]:
        """Persist the previously proposed plan update"""
        try:
            # Get the proposal
            proposal = self.pending_proposals.get(proposal_id)
            if not proposal:
                return {'error': f'Proposal {proposal_id} not found or expired'}

            day = proposal['day']
            action = proposal['action']
            block = proposal['block']

            conn = self.db.get_connection()
            cursor = conn.cursor()

            block_id = None

            if action == 'remove_block':
                # Handle block removal
                target_label = (proposal.get("target_label") 
                               or proposal.get("block", {}).get("label") 
                               or "").strip()
                target_id = proposal.get("target_block_id")  # optional

                # Get current day plan
                day_plan = self._get_weekly_plan(day)
                before_len = len(day_plan)

                def _label(b):
                    return (b.get("label") or b.get("exercise") or "").strip().casefold()

                # Build predicate: match by id if present, else by label (case-insensitive)
                conn = self.db.get_connection()
                cursor = conn.cursor()

                removed_count = 0
                if target_id:
                    # Remove by ID if provided
                    cursor.execute('DELETE FROM weekly_plan WHERE id = ? AND day_of_week = ?', (target_id, day))
                    removed_count = cursor.rowcount
                elif target_label:
                    # Remove by label (case-insensitive)
                    cursor.execute('DELETE FROM weekly_plan WHERE day_of_week = ? AND LOWER(exercise_name) = LOWER(?)', (day, target_label))
                    removed_count = cursor.rowcount

                conn.commit()
                conn.close()

                # Get updated plan for verification
                updated_plan = self._get_weekly_plan(day)

                print(f"REMOVE_BLOCK day={day} removed={removed_count} before={before_len} after={len(updated_plan)}")

                # Clean up the proposal
                del self.pending_proposals[proposal_id]

                return {
                    "status": "ok",
                    "block_id": None,
                    "wrote": bool(removed_count > 0),
                    "removed": removed_count,
                    "updated_plan": updated_plan
                }

            elif action == 'add_block':
                # Get next order if not specified
                if block['order_index'] == 99:
                    cursor.execute('SELECT COALESCE(MAX(exercise_order), 0) + 1 FROM weekly_plan WHERE day_of_week = ?', (day,))
                    block['order_index'] = cursor.fetchone()[0]

                if block['block_type'] == 'circuit':
                    # Insert circuit block
                    cursor.execute('''
                        INSERT INTO weekly_plan
                        (day_of_week, exercise_name, target_sets, target_reps, target_weight, exercise_order,
                         block_type, meta_json, members_json, created_by, newly_added, date_added)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (day, block['label'], 
                          block['meta_json'].get('rounds', 1), 
                          f"{len(block['members'])} exercises",
                          'circuit', 
                          block['order_index'],
                          'circuit', 
                          json.dumps(block['meta_json']), 
                          json.dumps(block['members']), 
                          'ai_v2', True, 
                          datetime.now().strftime('%Y-%m-%d')))

                    block_id = cursor.lastrowid
                else:
                    # Insert simple block
                    cursor.execute('''
                        INSERT INTO weekly_plan
                        (day_of_week, exercise_name, target_sets, target_reps, target_weight, exercise_order, created_by, newly_added, date_added)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (day, block['label'], 3, '8-12', 'bodyweight', block['order_index'], 'ai_v2', True, datetime.now().strftime('%Y-%m-%d')))

                    block_id = cursor.lastrowid

            conn.commit()
            conn.close()

            # Clean up the proposal
            del self.pending_proposals[proposal_id]

            print(f"COMMIT id={proposal_id} wrote=True block_id={block_id}")

            # Post-write verification
            updated_plan = self._get_weekly_plan(day)
            print(f"POST_WRITE_VERIFY day={day} blocks={len(updated_plan)}")

            return {
                'status': 'ok',
                'block_id': block_id,
                'wrote': True,
                'updated_plan': updated_plan
            }

        except Exception as e:
            return {'error': f'Failed to commit proposal: {str(e)}'}