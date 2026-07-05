"""
HIVE — Data Analyst Agent
CSV/JSON/Excel analysis with statistical computation and chart generation.
"""

import os
import json
import csv
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def _load_data(file_path: str) -> tuple[list[dict], list[str]]:
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".csv":
        with open(file_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            cols = reader.fieldnames or []
    elif ext == ".json":
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                rows = data
                cols = list(data[0].keys()) if data else []
            else:
                rows = [data]
                cols = list(data.keys())
    elif ext in (".xlsx", ".xls"):
        try:
            import pandas as pd
            df = pd.read_excel(file_path)
            rows = df.to_dict("records")
            cols = df.columns.tolist()
        except ImportError:
            return [], []
    else:
        return [], []

    return rows, cols


def _compute_stats(rows: list[dict], numeric_cols: list[str]) -> dict:
    import statistics

    if not rows:
        return {}

    numeric_data = {}
    str_cols = []

    for col in list(rows[0].keys()):
        vals = []
        for row in rows:
            try:
                vals.append(float(row.get(col, 0)))
                numeric_data[col] = vals
            except (ValueError, TypeError):
                str_cols.append(col)

    stats = {}
    for col, vals in numeric_data.items():
        if not vals:
            continue
        stats[col] = {
            "count": len(vals),
            "mean": round(statistics.mean(vals), 4),
            "median": round(statistics.median(vals), 4),
            "stdev": round(statistics.stdev(vals) if len(vals) > 1 else 0, 4),
            "min": round(min(vals), 4),
            "max": round(max(vals), 4),
        }

    return {"numeric": stats, "row_count": len(rows), "col_count": len(rows[0]) if rows else 0}


async def run(task: str) -> dict:
    from hive.core.llm_router import chat, QWEN_TURBO

    import re
    path_match = re.search(r'[A-Za-z]:[\\\/].*?\.(csv|json|xlsx|xls)', task)
    if not path_match:
        result = await chat(
            [{"role": "system", "content": "Extract any file path that looks like a CSV, JSON, or Excel file from the text."},
             {"role": "user", "content": task}],
            model=QWEN_TURBO,
            max_tokens=128,
        )
        path_match = re.search(r'[A-Za-z]:[\\\/].*?\.(csv|json|xlsx|xls)', result["content"])

    if not path_match:
        return {"status": "error", "message": "No data file found in task"}

    file_path = path_match.group(0)
    if not os.path.exists(file_path):
        return {"status": "error", "message": f"File not found: {file_path}"}

    rows, cols = _load_data(file_path)
    if not rows:
        return {"status": "error", "message": f"Could not load data from {file_path}"}

    stats = _compute_stats(rows, cols)

    insight_result = await chat(
        [{"role": "system", "content": "You are a data analyst. Analyze the data and provide key insights."},
         {"role": "user", "content": f"File: {file_path}\nRows: {len(rows)}\nColumns: {cols}\nStats: {stats}\n\nProvide 5 key insights from this data."}],
        model=QWEN_TURBO,
        max_tokens=768,
    )

    return {
        "status": "ok",
        "file": file_path,
        "rows_loaded": len(rows),
        "columns": cols,
        "statistics": stats,
        "insights": insight_result["content"],
    }
