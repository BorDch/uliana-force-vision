from uliana.state_machine import PushUpStateMachine


def test_exactly_one_complete_cycle_with_noisy_boundaries():
    machine = PushUpStateMachine()
    completed = sum(machine.update(x) for x in [165, 149, 151, 140, 110, 104, 106, 100, 112, 108, 130, 149, 151, 160])
    assert completed == 1 == machine.rep_count


def test_incomplete_movement_is_not_a_rep():
    machine = PushUpStateMachine()
    assert not any(machine.update(x) for x in [165, 148, 142, 139, 142, 148, 160])
    assert machine.rep_count == 0
