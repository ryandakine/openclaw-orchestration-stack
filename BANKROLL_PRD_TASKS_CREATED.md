# Bankroll Tracker PRD - Tasks Created Successfully

**Date:** 2026-03-09  
**Project:** poker-coach  
**PRD:** PRD_BANKROLL_TRACKER.md

---

## ✅ Taskmaster Tasks Created

### Summary
- **20 Tasks** created from PRD
- **200 Subtasks** (10 per task)
- **All tasks** follow the recommended build order from PRD Section 24

---

## Task List

| ID | Task | Priority | Dependencies |
|----|------|----------|--------------|
| 1 | Create bankroll_tracker.py core module | HIGH | - |
| 2 | Implement BankrollRuntimeState dataclass | HIGH | 1 |
| 3 | Create append-only event log system | HIGH | 1 |
| 4 | Implement idempotency handling | HIGH | 3 |
| 5 | Build async persistence queue | HIGH | 2,3,4 |
| 6 | Implement atomic snapshot writes | HIGH | 5 |
| 7 | Add session tracking | MEDIUM | 1 |
| 8 | Add startup recovery logic | HIGH | 3,6,7 |
| 9 | Integrate with hand_watcher.py | HIGH | 1,4,5 |
| 10 | Add bankroll logging to logger.py | MEDIUM | 1,3 |
| 11 | Update post_mortem_review.py | LOW | 7 |
| 12 | Add dashboard API endpoint /api/bankroll | HIGH | 2,6 |
| 13 | Create bankroll dashboard panel UI | MEDIUM | 12 |
| 14 | Implement manual adjustment endpoint | LOW | 12 |
| 15 | Integrate coach context | HIGH | 2,7 |
| 16 | Add CLI flags for testing | LOW | 1,8,14 |
| 17 | Write unit tests | HIGH | 1,2,3,4,5,6,7 |
| 18 | Write integration tests | HIGH | 9,12,17 |
| 19 | Write performance tests | MEDIUM | 17 |
| 20 | Update README documentation | LOW | 12,13,16 |

---

## Subtask Breakdown

Each task has 10 detailed subtasks. Example for Task 1:

### Task 1: Create bankroll_tracker.py core module
1. Create BankrollTracker class skeleton
2. Implement __init__ with default state
3. Add log_hand_result method signature
4. Add get_summary method signature
5. Add get_coach_context method signature
6. Add start_session method signature
7. Add close_session method signature
8. Add apply_manual_adjustment method
9. Add module-level documentation
10. Create initial unit tests

---

## Quick Start

```bash
cd ~/poker-coach

# View all bankroll tasks
task-master list

# Start first task
task-master set-status --id=1 --status=in-progress
task-master show 1

# Work through subtasks
# ... implement subtask 1 ...
# ... implement subtask 2 ...
# etc.

# Mark task complete
task-master set-status --id=1 --status=done
```

---

## PRD Requirements Covered

✅ Real-time performance (50ms updates, 25ms reads)  
✅ In-memory hot runtime state  
✅ Append-only event log (bankroll_events.jsonl)  
✅ Derived snapshot (bankroll.json)  
✅ Idempotent updates  
✅ Async persistence  
✅ Session tracking  
✅ Dashboard integration  
✅ Coach context  
✅ Manual adjustments  
✅ Full test coverage  

---

**Ready to implement! 🚀**
