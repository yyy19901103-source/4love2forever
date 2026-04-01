import mermaid_scheduler as ms


def test_parse_and_optimize():
    code = """
flowchart TD
    A --> B
    A --> C
    B --> D
    C --> D

gantt
    section Dev
    要件定義 :A, 2d
    設計 :B, 3d
    実装 :C, 5d
    テスト :D, 2d
"""
    plan = ms.parse_mermaid(code)
    scheduled = ms.optimize_schedule(plan.tasks, max_parallel_tasks=2)
    by_id = {t.task_id: t for t in scheduled}

    assert by_id["A"].start_day == 0
    assert by_id["D"].start_day >= by_id["B"].end_day
    assert by_id["D"].start_day >= by_id["C"].end_day


def test_run_returns_mermaid_blocks():
    code = """
flowchart TD
    A --> B

gantt
    section Dev
    Task A :A, 1d
    Task B :B, after A, 2d
"""
    out = ms.run(code, "2026-04-01", 1)
    assert "flowchart TD" in out["flowchart"]
    assert "gantt" in out["optimized_gantt"]
    assert out["project_duration_days"] == 3
