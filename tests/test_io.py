from __future__ import annotations

from pathlib import Path

import pytest
from conftest import DATA

from route_opt.baseline import greedy_nearest_neighbour
from route_opt.generator import (
    generate_instance,
    instance_to_dict,
    load_instance,
    load_solomon,
    save_instance,
    save_solomon,
)
from route_opt.validate import validate

SOLOMON_SNIPPET = """C101

VEHICLE
NUMBER     CAPACITY
  25         200

CUSTOMER
CUST NO.  XCOORD.   YCOORD.    DEMAND   READY TIME  DUE DATE   SERVICE   TIME

    0      40         50          0          0       1236          0
    1      45         68         10        912        967         90
    2      45         70         30        825        870         90
    3      42         66         10         65        146         90
    4      42         68         10        727        782         90
    5      42         65         10         15         67         90
"""


def test_json_round_trip(tmp_path: Path) -> None:
    inst = generate_instance(25, "C", seed=2, tw="loose")
    path = tmp_path / "inst.json"
    save_instance(inst, path)
    back = load_instance(path)
    assert instance_to_dict(back) == instance_to_dict(inst)
    assert (back.dist == inst.dist).all()


def test_solomon_round_trip(tmp_path: Path) -> None:
    inst = generate_instance(15, "R", seed=3)
    path = tmp_path / "inst.txt"
    save_solomon(inst, path)
    back = load_instance(path)  # .txt dispatches to the Solomon parser
    assert back.num_vehicles == inst.num_vehicles
    assert back.vehicle_capacity == inst.vehicle_capacity
    assert [(c.x, c.y, c.demand, c.ready_time, c.due_time, c.service_time) for c in back.customers] == [
        (c.x, c.y, c.demand, c.ready_time, c.due_time, c.service_time) for c in inst.customers
    ]
    assert (back.dist == inst.dist).all()


def test_parse_solomon_snippet(tmp_path: Path) -> None:
    path = tmp_path / "C101.txt"
    path.write_text(SOLOMON_SNIPPET)
    inst = load_solomon(path)
    assert inst.name == "C101"
    assert (inst.num_vehicles, inst.vehicle_capacity, inst.n) == (25, 200, 5)
    assert inst.depot.due_time == 1236
    assert inst.customers[2].ready_time == 65 and inst.customers[2].service_time == 90
    assert load_solomon(path, max_customers=3).n == 3


def test_parse_rejects_garbage(tmp_path: Path) -> None:
    path = tmp_path / "bad.txt"
    path.write_text("not an instance\n1 2 3\n")
    with pytest.raises(ValueError):
        load_solomon(path)


@pytest.mark.parametrize(
    "path", sorted(DATA.glob("*.json")) + sorted(DATA.glob("*.txt")), ids=lambda p: p.name
)
def test_bundled_demo_instances_load_and_are_feasible(path: Path) -> None:
    inst = load_instance(path)
    sol = greedy_nearest_neighbour(inst)
    assert validate(inst, sol).ok
