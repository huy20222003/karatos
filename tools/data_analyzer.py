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
    "description": "Professional Data Scientist: Deep analysis of CSV/Excel/JSON data using Pandas/NumPy.",
    "author": "Karatos Core",
    "version": "1.0.0",
    "enabled": True,
    "aliases": ["analyze_data", "statistics", "chart"],
    "class_name": "DataAnalyzer",
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
        import polars as pl

        # 1. Load data
        try:
            if file_path and os.path.exists(file_path):
                ext = os.path.splitext(file_path)[1].lower()
                if ext == ".csv":
                    df = pl.read_csv(file_path, n_rows=10000)
                elif ext in [".xlsx", ".xls"]:
                    # Using calamine engine for better compatibility
                    df = pl.read_excel(file_path, engine="calamine")
                else:
                    return {"status": "error", "message": f"Unsupported file type: {ext}"}
            elif data:
                df = pl.from_dicts(data)
            else:
                return {"status": "error", "message": "No data provided. Supply 'data' array or 'file_path'."}
        except Exception as e:
            return {"status": "error", "message": f"Failed to load data: {str(e)}"}

        logger.info(f"[DATA_ANALYZER] Loaded {len(df)} rows, {len(df.columns)} columns. Analysis: {analysis_type}")

        # 2. Statistical Summary
        if analysis_type == "summary":
            try:
                summary = {
                    "shape": {"rows": df.height, "columns": df.width},
                    "columns": df.columns,
                    "dtypes": {col: str(dtype) for col, dtype in zip(df.columns, df.dtypes)},
                    "missing_values": {col: count for col, count in zip(df.columns, df.null_count().row(0))},
                    "numeric_summary": {}
                }
                
                numeric_df = df.select(pl.col(pl.NUMERIC_DTYPES))
                if numeric_df.width > 0:
                    desc_df = numeric_df.describe()
                    stats = desc_df.to_dicts()
                    numeric_summary = {}
                    for col in numeric_df.columns:
                        numeric_summary[col] = {row['statistic']: row[col] for row in stats}
                    summary["numeric_summary"] = numeric_summary
                
                # Sample rows
                summary["sample_data"] = df.head(5).to_dicts()
                
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
                        ax.bar(df[x_column].to_list(), df[y_column].to_list(), color="#e94560")
                        ax.set_xlabel(x_column, color="white")
                        ax.set_ylabel(y_column, color="white")
                    else:
                        numeric_cols = df.select(pl.col(pl.NUMERIC_DTYPES)).columns
                        if numeric_cols:
                            df.head(20)[numeric_cols[0]].to_pandas().plot(kind="bar", ax=ax, color="#e94560")
                elif chart_type == "line":
                    if x_column and y_column:
                        ax.plot(df[x_column].to_list(), df[y_column].to_list(), color="#e94560", linewidth=2)
                        ax.set_xlabel(x_column, color="white")
                        ax.set_ylabel(y_column, color="white")
                    else:
                        numeric_cols = df.select(pl.col(pl.NUMERIC_DTYPES)).columns
                        for col in numeric_cols[:3]:
                            ax.plot(df[col].to_list(), label=col)
                        ax.legend()
                elif chart_type == "pie":
                    col = y_column or df.select(pl.col(pl.NUMERIC_DTYPES)).columns[0]
                    data_slice = df.head(10)
                    ax.pie(data_slice[col].to_list(), labels=data_slice[df.columns[0]].to_list() if len(df.columns) > 1 else None, autopct="%1.1f%%")
                elif chart_type == "scatter":
                    if x_column and y_column:
                        ax.scatter(df[x_column].to_list(), df[y_column].to_list(), color="#e94560", alpha=0.7)
                        ax.set_xlabel(x_column, color="white")
                        ax.set_ylabel(y_column, color="white")
                elif chart_type == "histogram":
                    col = y_column or x_column or df.select(pl.col(pl.NUMERIC_DTYPES)).columns[0]
                    ax.hist(df[col].to_list(), bins=30, color="#e94560", edgecolor="#0f3460")
                    ax.set_xlabel(col, color="white")

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
                numeric_df = df.select(pl.col(pl.NUMERIC_DTYPES))
                if numeric_df.width < 2:
                    return {"status": "error", "message": "Need at least 2 numeric columns for correlation."}
                
                # Polars correlation matrix is a bit different, we can compute it manually or use .corr()
                corr_df = numeric_df.corr()
                # Convert to dict {col: {other_col: val}}
                corr_dict = {}
                cols = corr_df.columns
                for i, row in enumerate(corr_df.to_dicts()):
                    corr_dict[cols[i]] = row
                return {"status": "success", "data": {"correlation_matrix": corr_dict}}
            except Exception as e:
                return {"status": "error", "message": f"Correlation analysis failed: {str(e)}"}

        return {"status": "error", "message": f"Unknown analysis type: {analysis_type}"}
