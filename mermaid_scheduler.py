from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from collections import defaultdict, deque
from dataclasses import dataclass, asdict
from typing import Dict, Iterable, List, Tuple


EDGE_RE = re.compile(r"^\s*([A-Za-z0-9_]+)\s*[-.=]+>\s*\|?.*?\|?\s*([A-Za-z0-9_]+)\s*$")
TASK_RE = re.compile(
    r"^\s*([^:]+?)\s*:\s*([A-Za-z0-9_]+)\s*,\s*(?:after\s+([A-Za-z0-9_]+)\s*,\s*)?(\d+)d\s*$",
    re.IGNORECASE,
)


@dataclass
class Task:
    name: str
    task_id: str
    duration_days: int
    dependencies: List[str]


@dataclass
class ScheduledTask(Task):
    start_day: int
    end_day: int


@dataclass
class Plan:
    flowchart_edges: List[Tuple[str, str]]
    tasks: List[Task]


def parse_mermaid(mermaid_code: str) -> Plan:
    """Parse a mixed Mermaid text that may contain flowchart and gantt blocks."""
    edges: List[Tuple[str, str]] = []
    tasks: List[Task] = []

    for line in mermaid_code.splitlines():
        edge_match = EDGE_RE.match(line)
        if edge_match:
            edges.append((edge_match.group(1), edge_match.group(2)))
            continue

        task_match = TASK_RE.match(line)
        if task_match:
            name, task_id, dep, duration = task_match.groups()
            tasks.append(
                Task(
                    name=name.strip(),
                    task_id=task_id,
                    duration_days=int(duration),
                    dependencies=[dep] if dep else [],
                )
            )

    # Merge explicit flowchart dependencies into tasks when IDs overlap
    dep_map: Dict[str, List[str]] = defaultdict(list)
    for src, dst in edges:
        dep_map[dst].append(src)

    task_ids = {task.task_id for task in tasks}
    merged: List[Task] = []
    for task in tasks:
        inferred = [d for d in dep_map.get(task.task_id, []) if d in task_ids]
        merged_deps = sorted(set(task.dependencies + inferred))
        merged.append(
            Task(
                name=task.name,
                task_id=task.task_id,
                duration_days=task.duration_days,
                dependencies=merged_deps,
            )
        )

    return Plan(flowchart_edges=edges, tasks=merged)


def _topological_order(tasks: Iterable[Task]) -> List[str]:
    task_list = list(tasks)
    by_id = {t.task_id: t for t in task_list}
    indegree = {t.task_id: 0 for t in task_list}
    graph: Dict[str, List[str]] = defaultdict(list)

    for task in task_list:
        for dep in task.dependencies:
            if dep not in by_id:
                continue
            graph[dep].append(task.task_id)
            indegree[task.task_id] += 1

    q = deque(sorted([tid for tid, deg in indegree.items() if deg == 0]))
    ordered: List[str] = []

    while q:
        node = q.popleft()
        ordered.append(node)
        for nxt in sorted(graph.get(node, [])):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                q.append(nxt)

    if len(ordered) != len(task_list):
        raise ValueError("依存関係に循環があります。Mermaidコードを確認してください。")
    return ordered


def optimize_schedule(tasks: List[Task], max_parallel_tasks: int = 2) -> List[ScheduledTask]:
    """Simple resource-constrained list scheduling.

    - respects dependencies
    - caps concurrent running tasks by max_parallel_tasks
    - prioritizes tasks by earliest possible start and longer duration
    """
    if max_parallel_tasks < 1:
        raise ValueError("max_parallel_tasks は 1 以上にしてください。")

    ordered = _topological_order(tasks)
    by_id = {t.task_id: t for t in tasks}
    dependents: Dict[str, List[str]] = defaultdict(list)
    remaining_deps_count: Dict[str, int] = {t.task_id: 0 for t in tasks}

    for t in tasks:
        for dep in t.dependencies:
            if dep in by_id:
                dependents[dep].append(t.task_id)
                remaining_deps_count[t.task_id] += 1

    ready = [tid for tid in ordered if remaining_deps_count[tid] == 0]
    ready_set = set(ready)
    active: List[Tuple[str, int]] = []  # (task_id, end_day)
    finished: set[str] = set()
    start_end: Dict[str, Tuple[int, int]] = {}
    current_day = 0

    def earliest_start(task: Task) -> int:
        if not task.dependencies:
            return 0
        end_days = [start_end[d][1] for d in task.dependencies if d in start_end]
        return max(end_days) if end_days else 0

    while len(finished) < len(tasks):
        while len(active) < max_parallel_tasks and ready:
            ready.sort(
                key=lambda tid: (
                    earliest_start(by_id[tid]),
                    -by_id[tid].duration_days,
                    tid,
                )
            )
            tid = ready.pop(0)
            ready_set.remove(tid)
            task = by_id[tid]
            start = max(current_day, earliest_start(task))
            end = start + task.duration_days
            start_end[tid] = (start, end)
            active.append((tid, end))

        if not active:
            current_day += 1
            continue

        active.sort(key=lambda x: x[1])
        next_tid, next_end = active.pop(0)
        current_day = next_end
        finished.add(next_tid)

        for child in dependents.get(next_tid, []):
            remaining_deps_count[child] -= 1
            if remaining_deps_count[child] == 0 and child not in ready_set and child not in finished:
                ready.append(child)
                ready_set.add(child)

    scheduled: List[ScheduledTask] = []
    for tid in ordered:
        task = by_id[tid]
        start, end = start_end[tid]
        scheduled.append(
            ScheduledTask(
                name=task.name,
                task_id=task.task_id,
                duration_days=task.duration_days,
                dependencies=task.dependencies,
                start_day=start,
                end_day=end,
            )
        )
    return scheduled


def to_mermaid_flowchart(edges: List[Tuple[str, str]]) -> str:
    lines = ["flowchart TD"]
    if not edges:
        lines.append("    A[No Graph] --> B[No Edges]")
    for src, dst in edges:
        lines.append(f"    {src} --> {dst}")
    return "\n".join(lines)


def to_mermaid_gantt(scheduled: List[ScheduledTask], start_date: dt.date) -> str:
    lines = [
        "gantt",
        "    title Optimized Schedule",
        "    dateFormat YYYY-MM-DD",
        "    axisFormat %m/%d",
        "    section Plan",
    ]
    for t in scheduled:
        start = start_date + dt.timedelta(days=t.start_day)
        lines.append(
            f"    {t.name} :{t.task_id}, {start.isoformat()}, {t.duration_days}d"
        )
    return "\n".join(lines)


def run(mermaid_code: str, start_date: str, max_parallel_tasks: int) -> dict:
    plan = parse_mermaid(mermaid_code)
    scheduled = optimize_schedule(plan.tasks, max_parallel_tasks=max_parallel_tasks)
    start = dt.date.fromisoformat(start_date)

    return {
        "flowchart": to_mermaid_flowchart(plan.flowchart_edges),
        "optimized_gantt": to_mermaid_gantt(scheduled, start),
        "schedule": [asdict(task) for task in scheduled],
        "project_duration_days": max((t.end_day for t in scheduled), default=0),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mermaidコードからフローチャートと最適化済みガントチャートを生成します。"
    )
    parser.add_argument("input", help="Mermaidテキストファイル")
    parser.add_argument("--start-date", default=dt.date.today().isoformat())
    parser.add_argument("--max-parallel", type=int, default=2)
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")

    args = parser.parse_args()
    with open(args.input, "r", encoding="utf-8") as f:
        mermaid_code = f.read()

    result = run(
        mermaid_code=mermaid_code,
        start_date=args.start_date,
        max_parallel_tasks=args.max_parallel,
    )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    print("# Flowchart\n")
    print("```mermaid")
    print(result["flowchart"])
    print("```\n")

    print("# Optimized Gantt\n")
    print("```mermaid")
    print(result["optimized_gantt"])
    print("```\n")

    print(f"Project Duration: {result['project_duration_days']} days")


if __name__ == "__main__":
    main()
