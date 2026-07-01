"""Quick import test for Phase 2 core modules."""
import sys
sys.path.insert(0, '.')

tests = []

# 1. agent_personality
try:
    from core.agent_personality import PERSONALITIES, get_personality
    tests.append(('agent_personality', True, f'{len(PERSONALITIES)} personalities'))
except Exception as e:
    tests.append(('agent_personality', False, str(e)))

# 2. economy
try:
    from core.economy import economy, COSTS, get_economy
    tests.append(('economy', True, f'budget={economy.budget.total}'))
except Exception as e:
    tests.append(('economy', False, str(e)))

# 3. agent_state
try:
    from core.agent_state import get_or_create_state, agent_registry
    state = get_or_create_state('leader')
    tests.append(('agent_state', True, f'leader conf={state.confidence}'))
except Exception as e:
    tests.append(('agent_state', False, str(e)))

# 4. arena
try:
    from core.arena import arena, ArenaMode
    tests.append(('arena', True, 'OK'))
except Exception as e:
    tests.append(('arena', False, str(e)))

# 5. dashboard_events
try:
    from core.dashboard_events import get_event_stream
    tests.append(('dashboard_events', True, 'OK'))
except Exception as e:
    tests.append(('dashboard_events', False, str(e)))

# 6. leader
try:
    from agents.leader import run_swarm, get_hive_status
    tests.append(('leader', True, 'OK'))
except Exception as e:
    tests.append(('leader', False, str(e)))

# 7. agent_forge
try:
    from agents.agent_forge import AgentForge
    tests.append(('agent_forge', True, 'OK'))
except Exception as e:
    tests.append(('agent_forge', False, str(e)))

# 8. cleanup_crew
try:
    from agents.cleanup_crew import CleanupCrew, cleanup_crew
    tests.append(('cleanup_crew', True, type(cleanup_crew).__name__))
except Exception as e:
    tests.append(('cleanup_crew', False, str(e)))

# Print results
for name, ok, detail in tests:
    status = 'OK' if ok else 'FAIL'
    print(f'  {name}: {status} - {detail}')

passed = sum(1 for _, ok, _ in tests if ok)
print(f'\n{passed}/{len(tests)} modules OK')