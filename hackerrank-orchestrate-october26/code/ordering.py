from typing import List, Dict, Any
from config import OPERATION_TO_PRIORITY_INDEX, PHASE_ORDER_INDEX

def order_and_renumber_steps(steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Stage 10 — Deterministic Ordering & Renumbering Layer:
    1. Partition steps into three phase buckets: FINDING, REMEDIATION, VERIFICATION.
    2. Within each phase, sort by:
       a. operation priority index (from config.OPERATION_PRIORITY)
       b. system_id ascending
       c. resource_id ascending
    3. Concatenate buckets in strict phase order.
    4. Renumber step_no sequentially starting from 1.
    """
    if not steps:
        return []

    # Sort key function
    def sort_key(s: Dict[str, Any]):
        phase = s.get('phase', '')
        phase_idx = PHASE_ORDER_INDEX.get(phase, 99)
        op = s.get('operation', '')
        op_idx = OPERATION_TO_PRIORITY_INDEX.get(op, 999)
        system_id = str(s.get('system_id', ''))
        resource_id = str(s.get('resource_id', ''))
        return (phase_idx, op_idx, system_id, resource_id)

    sorted_steps = sorted(steps, key=sort_key)

    # Renumber step_no consecutively starting at 1
    result = []
    for idx, s in enumerate(sorted_steps, start=1):
        step_obj = {
            "step_no": idx,
            "phase": s["phase"],
            "system_id": s["system_id"],
            "resource_id": s["resource_id"],
            "operation": s["operation"],
            "state": s["state"],
            "evidence_id": s.get("evidence_id", "")
        }
        result.append(step_obj)

    return result

def test_ordering():
    from config import OPERATION_PRIORITY
    import random
    
    # Construct synthetic unsorted steps covering every single operation
    synthetic_steps = []
    for item in OPERATION_PRIORITY:
        phase, op, st = item
        synthetic_steps.append({
            "step_no": 999,
            "phase": phase,
            "system_id": "service_b",
            "resource_id": "res_2",
            "operation": op,
            "state": st,
            "evidence_id": "ev_1" if phase == "FINDING" else ""
        })
        synthetic_steps.append({
            "step_no": 999,
            "phase": phase,
            "system_id": "service_a",
            "resource_id": "res_1",
            "operation": op,
            "state": st,
            "evidence_id": "ev_1" if phase == "FINDING" else ""
        })
        
    # Shuffle randomly
    shuffled = list(synthetic_steps)
    random.seed(42)
    random.shuffle(shuffled)
    
    # Sort
    ordered = order_and_renumber_steps(shuffled)
    assert len(ordered) == len(synthetic_steps)
    
    # Assert consecutive step_no
    for i, s in enumerate(ordered, start=1):
        assert s["step_no"] == i
        
    # Assert phase and op priority order
    for i in range(len(ordered) - 1):
        s1 = ordered[i]
        s2 = ordered[i+1]
        p1 = PHASE_ORDER_INDEX[s1['phase']]
        p2 = PHASE_ORDER_INDEX[s2['phase']]
        assert p1 <= p2
        if p1 == p2:
            op1 = OPERATION_TO_PRIORITY_INDEX[s1['operation']]
            op2 = OPERATION_TO_PRIORITY_INDEX[s2['operation']]
            assert op1 <= op2
            if op1 == op2:
                assert s1['system_id'] <= s2['system_id']
                if s1['system_id'] == s2['system_id']:
                    assert s1['resource_id'] <= s2['resource_id']
                    
    print("Ordering unit test passed successfully!")

if __name__ == "__main__":
    test_ordering()
