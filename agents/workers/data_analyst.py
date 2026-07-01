"""
HIVE — Data Analyst Agent
CSV/JSON/Excel analysis with statistical computation and chart generation.
"""

import os
import json
import csv
import logging
from io import StringIO
from typing import Optional

logger = logging.getLogger(__name__)


def _load_data(file_path: str) -> tuple[list[dict], list[str]]:
    """Load data from CSV, JSON, or Excel file."""
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
    """Compute statistical summary."""
    import statistics

    if not rows:
        return {}

    # Find numeric columns
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
            "p25": round(sorted(vals)[len(vals) // 4], 4),
            "p75": round(sorted(vals)[3 * len(vals) // 4], 4),
        }

    # String column analysis
    str_stats = {}
    for col in str_cols:
        vals = [str(row.get(col, "")) for row in rows if row.get(col)]
        if vals:
            str_stats[col] = {
                "unique_count": len(set(vals)),
                "most_common": max(set(vals), key=vals.count) if vals else "",
                "sample": vals[:3],
            }

    return {"numeric": stats, "string": str_stats, "row_count": len(rows), "col_count": len(rows[0]) if rows else 0}


def _generate_charts(rows: list[dict], numeric_cols: list[str], output_dir: str = "static") -> list[str]:
    """Generate matplotlib charts and save to static/ folder."""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import pandas as pd
    except ImportError:
        return []

    os.makedirs(output_dir, exist_ok=True)
    chart_paths = []

    try:
        df = pd.DataFrame(rows)
        numeric = df.select_dtypes(include="number").columns.tolist()

        # Histogram for first numeric column
        if numeric:
            col = numeric[0]
            fig, ax = plt.subplots()
            df[col].hist(ax=ax, bins=20, edgecolor='black')
            ax.set_title(f"Distribution: {col}")
            ax.set_xlabel(col)
            ax.set_ylabel("Frequency")
            path = f"{output_dir}/hist_{col}.png"
            fig.savefig(path, dpi=100)
            plt.close(fig)
            chart_paths.append(path)

        # Bar chart for first categorical column
        str_cols = df.select_dtypes(include="object").columns.tolist()
        if str_cols and len(rows) < 1000:
            col = str_cols[0]
            fig, ax = plt.subplots()
            df[col].value_counts().head(10).plot(kind='bar', ax=ax)
            ax.set_title(f"Top 10: {col}")
            ax.set_ylabel("Count")
            plt.xticks(rotation=45, ha='right')
            path = f"{output_dir}/bar_{col}.png"
            fig.savefig(path, dpi=100)
            plt.close(fig)
            chart_paths.append(path)

        # Correlation heatmap
        if len(numeric) >= 2:
            fig, ax = plt.subplots()
            corr = df[numeric].corr()
            im = ax.imshow(corr, cmap='coolwarm', aspect='auto', vmin=-1, vmax=1)
            ax.set_xticks(range(len(numeric)))
            ax.set_yticks(range(len(numeric)))
            ax.set_xticklabels(numeric, rotation=45, ha='right')
            ax.set_yticklabels(numeric)
            plt.colorbar(im, ax=ax)
            ax.set_title("Correlation Matrix")
            path = f"{output_dir}/correlation.png"
            fig.savefig(path, dpi=100)
            plt.close(fig)
            chart_paths.append(path)
    except Exception as e:
        logger.warning(f"Chart generation error: {e}")

    return chart_paths


async def run(task: str) -> dict:
    """Analyze data from a file."""
    from core.llm_router import chat, QWEN_TURBO

    # Extract file path from task
    import re
    path_match = re.search(r'[A-Za-z]:[\\\/].*?\.(csv|json|xlsx|xls)', task)
    if not path_match:
        # Try to find it another way
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

    # Compute stats
    stats = _compute_stats(rows, cols)

    # Generate charts
    chart_paths = _generate_charts(rows, cols)

    # Get LLM insights
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
        "charts": chart_paths,
        "insights": insight_result["content"],
    }