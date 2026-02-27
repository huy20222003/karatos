"""
Data Analyzer Tool
Analyzes data, generates statistics, and creates charts.
"""
import os
import json
import asyncio
from typing import Any, Dict
from datetime import datetime

from utils.logger import get_logger

logger = get_logger()

TOOL_META = {
    "name": "data_analyzer",
    "aliases": ["analyze_data", "statistics", "chart"],
    "class_name": "DataAnalyzer",
    "description": "Data Analyzer: Performs statistical analysis and creates charts from structured data (JSON, CSV, query results).",
    "actions": [
        {
            "name": "analyze_data",
            "description": "Analyze data and generate statistics/charts.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "data": {"type": "array", "description": "Array of data objects/rows to analyze."},
                    "file_path": {"type": "string", "description": "Path to CSV/Excel file to analyze."},
                    "analysis_type": {"type": "string", "enum": ["summary", "chart", "correlation"], "description": "Type of analysis."},
                    "chart_type": {"type": "string", "enum": ["bar", "line", "pie", "scatter", "histogram"], "description": "Chart type if analysis_type is 'chart'."},
                    "x_column": {"type": "string", "description": "Column for X axis."},
                    "y_column": {"type": "string", "description": "Column for Y axis."},
                    "title": {"type": "string", "description": "Chart title."}
                }
            }
        }
    ]
}


class DataAnalyzer:
    """Data analysis and visualization engine."""

    @classmethod
    async def execute(cls, data: list = None, file_path: str = "",
                      analysis_type: str = "summary",
                      chart_type: str = "bar",
                      x_column: str = "", y_column: str = "",
                      title: str = "", **kwargs) -> Dict[str, Any]:
        """Analyze data and optionally create charts."""
        import pandas as pd

        # 1. Load data
        try:
            if file_path and os.path.exists(file_path):
                ext = os.path.splitext(file_path)[1].lower()
                if ext == ".csv":
                    df = pd.read_csv(file_path, nrows=10000)
                elif ext in [".xlsx", ".xls"]:
                    df = pd.read_excel(file_path, nrows=10000)
                else:
                    return {"status": "error", "message": f"Unsupported file type: {ext}"}
            elif data:
                df = pd.DataFrame(data)
            else:
                return {"status": "error", "message": "No data provided. Supply 'data' array or 'file_path'."}
        except Exception as e:
            return {"status": "error", "message": f"Failed to load data: {str(e)}"}

        logger.info(f"[DATA_ANALYZER] Loaded {len(df)} rows, {len(df.columns)} columns. Analysis: {analysis_type}")

        # 2. Statistical Summary
        if analysis_type == "summary":
            try:
                summary = {
                    "shape": {"rows": len(df), "columns": len(df.columns)},
                    "columns": list(df.columns),
                    "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
                    "missing_values": df.isnull().sum().to_dict(),
                    "numeric_summary": {}
                }
                numeric_cols = df.select_dtypes(include=["number"]).columns
                if len(numeric_cols) > 0:
                    desc = df[numeric_cols].describe().to_dict()
                    summary["numeric_summary"] = {
                        col: {k: round(v, 4) if isinstance(v, float) else v for k, v in stats.items()}
                        for col, stats in desc.items()
                    }
                # Sample rows
                summary["sample_data"] = df.head(5).to_dict(orient="records")
                
                return {"status": "success", "data": summary}
            except Exception as e:
                return {"status": "error", "message": f"Summary analysis failed: {str(e)}"}

        # 3. Chart Generation
        elif analysis_type == "chart":
            try:
                import matplotlib
                matplotlib.use("Agg")
                import matplotlib.pyplot as plt

                fig, ax = plt.subplots(figsize=(10, 6))
                fig.patch.set_facecolor("#1a1a2e")
                ax.set_facecolor("#16213e")

                chart_title = title or f"{chart_type.title()} Chart"

                if chart_type == "bar":
                    if x_column and y_column:
                        df.plot(kind="bar", x=x_column, y=y_column, ax=ax, color="#e94560")
                    else:
                        df.select_dtypes(include=["number"]).iloc[:20].plot(kind="bar", ax=ax)
                elif chart_type == "line":
                    if x_column and y_column:
                        df.plot(kind="line", x=x_column, y=y_column, ax=ax, color="#e94560", linewidth=2)
                    else:
                        df.select_dtypes(include=["number"]).plot(kind="line", ax=ax)
                elif chart_type == "pie":
                    col = y_column or df.select_dtypes(include=["number"]).columns[0]
                    df[col].head(10).plot(kind="pie", ax=ax, autopct="%1.1f%%")
                elif chart_type == "scatter":
                    if x_column and y_column:
                        df.plot(kind="scatter", x=x_column, y=y_column, ax=ax, color="#e94560", alpha=0.7)
                elif chart_type == "histogram":
                    col = y_column or x_column or df.select_dtypes(include=["number"]).columns[0]
                    df[col].plot(kind="hist", ax=ax, bins=30, color="#e94560", edgecolor="#0f3460")

                ax.set_title(chart_title, color="white", fontsize=14, fontweight="bold")
                ax.tick_params(colors="white")
                for spine in ax.spines.values():
                    spine.set_color("#0f3460")
                
                # Save chart
                chart_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "charts")
                os.makedirs(chart_dir, exist_ok=True)
                chart_path = os.path.join(chart_dir, f"chart_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
                plt.tight_layout()
                plt.savefig(chart_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
                plt.close(fig)

                logger.info(f"[DATA_ANALYZER] Chart saved: {chart_path}")
                return {
                    "status": "success",
                    "data": {"chart_path": chart_path, "chart_type": chart_type},
                    "photo": chart_path
                }
            except Exception as e:
                logger.error(f"[DATA_ANALYZER] Chart generation failed: {e}")
                return {"status": "error", "message": f"Chart generation failed: {str(e)}"}

        # 4. Correlation
        elif analysis_type == "correlation":
            try:
                numeric_df = df.select_dtypes(include=["number"])
                if numeric_df.empty:
                    return {"status": "error", "message": "No numeric columns found for correlation analysis."}
                corr = numeric_df.corr().round(4).to_dict()
                return {"status": "success", "data": {"correlation_matrix": corr}}
            except Exception as e:
                return {"status": "error", "message": f"Correlation analysis failed: {str(e)}"}

        return {"status": "error", "message": f"Unknown analysis type: {analysis_type}"}
