"""
Chart Generator Tool
Professional chart/graph generation supporting a wide range of visualization types.
Produces publication-quality PNG images with a modern dark theme.
"""
import os
import io
import json
import asyncio
from typing import Any, Dict, List, Optional
from datetime import datetime

from utils.logger import get_logger

logger = get_logger()

TOOL_META = {
    "name": "chart_generator",
    "description": "Professional Chart Engine: Generates high-quality data visualizations. Supports bar, line, pie, donut, heatmap, radar, scatter, histogram, waterfall, funnel, treemap charts — and COMBO mode to combine multiple chart types (e.g., bar + line) on the same axes.",
    "author": "Karatos Core",
    "version": "1.0.0",
    "enabled": True,
    "aliases": ["draw_chart", "generate_chart", "visualize", "plot", "vẽ_biểu_đồ"],
    "class_name": "ChartGenerator",
    "actions": [
        {
            "name": "generate_chart",
            "description": "Generate a chart/graph from data. Returns a PNG image.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "chart_type": {
                        "type": "string",
                        "enum": ["bar", "line", "pie", "donut", "heatmap", "radar",
                                 "scatter", "histogram", "waterfall", "funnel",
                                 "treemap", "combo"],
                        "description": "Type of chart to generate."
                    },
                    "data": {
                        "type": "array",
                        "description": "Array of data objects. Each object is a row with named fields."
                    },
                    "title": {"type": "string", "description": "Chart title."},
                    "x_column": {"type": "string", "description": "Column name for X axis / labels."},
                    "y_column": {"type": "string", "description": "Column name for Y axis / values."},
                    "y_columns": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Multiple Y columns for combo/multi-series charts."
                    },
                    "series": {
                        "type": "array",
                        "description": "For combo charts: [{name, type, y_column}] defining each series."
                    },
                    "colors": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Custom color palette (hex codes)."
                    },
                    "show_values": {"type": "boolean", "description": "Show value labels on chart."},
                    "width": {"type": "integer", "description": "Chart width in pixels."},
                    "height": {"type": "integer", "description": "Chart height in pixels."}
                },
                "required": ["chart_type", "data"]
            }
        }
    ]
}

# ──────────────────────────────────────────────
# THEME — Modern Dark Professional
# ──────────────────────────────────────────────
DARK_THEME = {
    "bg": "#0f0f1a",
    "panel": "#1a1a2e",
    "grid": "#2a2a4a",
    "text": "#e0e0e0",
    "title": "#ffffff",
    "accent": "#e94560",
    "palette": [
        "#e94560", "#0f3460", "#16c79a", "#f5a623",
        "#b721ff", "#21d4fd", "#ff6b6b", "#48dbfb",
        "#feca57", "#ff9ff3", "#54a0ff", "#5f27cd",
        "#01a3a4", "#2ed573", "#ff4757", "#7bed9f"
    ]
}


class ChartGenerator:
    """Professional chart generation engine with comprehensive chart type support."""

    @staticmethod
    def _setup_matplotlib():
        """Configure matplotlib for headless rendering."""
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.font_manager as fm

        plt.rcParams.update({
            "figure.facecolor": DARK_THEME["bg"],
            "axes.facecolor": DARK_THEME["panel"],
            "axes.edgecolor": DARK_THEME["grid"],
            "axes.labelcolor": DARK_THEME["text"],
            "axes.grid": True,
            "grid.color": DARK_THEME["grid"],
            "grid.alpha": 0.3,
            "xtick.color": DARK_THEME["text"],
            "ytick.color": DARK_THEME["text"],
            "text.color": DARK_THEME["text"],
            "figure.dpi": 150,
            "savefig.dpi": 150,
            "font.size": 11,
        })
        return plt

    @staticmethod
    def _get_colors(n: int, custom: list = None) -> list:
        """Get n colors from custom palette or default theme."""
        palette = custom if custom else DARK_THEME["palette"]
        return [palette[i % len(palette)] for i in range(n)]

    @staticmethod
    def _to_bytes(fig, plt) -> bytes:
        """Convert matplotlib figure to PNG bytes."""
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight",
                    facecolor=fig.get_facecolor(), edgecolor="none")
        plt.close(fig)
        buf.seek(0)
        return buf.read()

    @staticmethod
    def _save_and_return(fig, plt) -> Dict[str, Any]:
        """Save chart to file AND return bytes for Telegram photo."""
        photo_bytes = ChartGenerator._to_bytes(fig, plt)

        chart_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "charts")
        os.makedirs(chart_dir, exist_ok=True)
        chart_path = os.path.join(chart_dir, f"chart_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")

        with open(chart_path, "wb") as f:
            f.write(photo_bytes)

        return {
            "status": "success",
            "data": {"chart_path": chart_path},
            "photo": photo_bytes,
            "message": f"Chart generated successfully."
        }

    # ══════════════════════════════════════════
    # MAIN ENTRY POINT
    # ══════════════════════════════════════════
    @classmethod
    async def execute(cls, chart_type: str = "bar", data: list = None,
                      title: str = "", x_column: str = "", y_column: str = "",
                      y_columns: list = None, series: list = None,
                      colors: list = None, show_values: bool = False,
                      width: int = 1000, height: int = 600,
                      **kwargs) -> Dict[str, Any]:
        """Generate a chart from input data."""

        if not data:
            return {"status": "error", "message": "No data provided. Supply a 'data' array."}

        chart_type = chart_type.lower().strip()
        plt = cls._setup_matplotlib()

        figsize = (width / 100, height / 100)

        try:
            dispatch = {
                "bar": cls._chart_bar,
                "line": cls._chart_line,
                "pie": cls._chart_pie,
                "donut": cls._chart_donut,
                "heatmap": cls._chart_heatmap,
                "radar": cls._chart_radar,
                "scatter": cls._chart_scatter,
                "histogram": cls._chart_histogram,
                "waterfall": cls._chart_waterfall,
                "funnel": cls._chart_funnel,
                "treemap": cls._chart_treemap,
                "combo": cls._chart_combo,
            }

            handler = dispatch.get(chart_type)
            if not handler:
                supported = ", ".join(dispatch.keys())
                return {"status": "error", "message": f"Unsupported chart type: '{chart_type}'. Supported: {supported}"}

            fig = handler(plt, data, title=title, x_column=x_column,
                         y_column=y_column, y_columns=y_columns,
                         series=series, colors=colors,
                         show_values=show_values, figsize=figsize)

            return cls._save_and_return(fig, plt)

        except Exception as e:
            logger.error(f"[CHART_GENERATOR] Failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {"status": "error", "message": f"Chart generation failed: {str(e)}"}

    # ══════════════════════════════════════════
    # CHART IMPLEMENTATIONS
    # ══════════════════════════════════════════

    @staticmethod
    def _auto_detect_columns(data: list, x_column: str, y_column: str, y_columns: list = None):
        """Auto-detect x and y columns from data if not specified."""
        if not data:
            return x_column, y_column, y_columns or []

        keys = list(data[0].keys()) if isinstance(data[0], dict) else []

        # Find numeric and non-numeric columns
        numeric_cols = []
        label_cols = []
        for k in keys:
            sample_val = data[0].get(k)
            if isinstance(sample_val, (int, float)):
                numeric_cols.append(k)
            else:
                label_cols.append(k)

        if not x_column:
            x_column = label_cols[0] if label_cols else (keys[0] if keys else "index")
        if not y_column and not y_columns:
            y_column = numeric_cols[0] if numeric_cols else (keys[1] if len(keys) > 1 else keys[0])
        if not y_columns:
            y_columns = []

        return x_column, y_column, y_columns

    @staticmethod
    def _extract_values(data: list, column: str) -> list:
        """Extract values for a column from data array."""
        if not data or not column:
            return []
        result = []
        for row in data:
            if isinstance(row, dict):
                val = row.get(column)
                result.append(val if val is not None else 0)
            else:
                result.append(row)
        return result

    # ─────────── BAR ───────────
    @classmethod
    def _chart_bar(cls, plt, data, title="", x_column="", y_column="",
                   y_columns=None, colors=None, show_values=False, figsize=(10, 6), **kw):
        x_column, y_column, y_columns = cls._auto_detect_columns(data, x_column, y_column, y_columns)
        labels = cls._extract_values(data, x_column)
        fig, ax = plt.subplots(figsize=figsize)

        if y_columns and len(y_columns) > 1:
            # Grouped bar
            import numpy as np
            x_pos = np.arange(len(labels))
            n = len(y_columns)
            w = 0.8 / n
            clrs = cls._get_colors(n, colors)
            for i, yc in enumerate(y_columns):
                vals = [float(v) for v in cls._extract_values(data, yc)]
                bars = ax.bar(x_pos + i * w - (n - 1) * w / 2, vals, w, label=yc, color=clrs[i])
                if show_values:
                    for bar in bars:
                        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                                f'{bar.get_height():.1f}', ha='center', va='bottom',
                                color=DARK_THEME["text"], fontsize=8)
            ax.set_xticks(x_pos)
            ax.set_xticklabels([str(l) for l in labels], rotation=45, ha='right')
            ax.legend(facecolor=DARK_THEME["panel"], edgecolor=DARK_THEME["grid"])
        else:
            vals = [float(v) for v in cls._extract_values(data, y_column)]
            clrs = cls._get_colors(len(vals), colors)
            bars = ax.bar([str(l) for l in labels], vals, color=clrs)
            ax.set_xlabel(x_column)
            ax.set_ylabel(y_column)
            plt.xticks(rotation=45, ha='right')
            if show_values:
                for bar in bars:
                    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                            f'{bar.get_height():.1f}', ha='center', va='bottom',
                            color=DARK_THEME["text"], fontsize=9)

        ax.set_title(title or "Bar Chart", color=DARK_THEME["title"], fontsize=14, fontweight="bold", pad=15)
        plt.tight_layout()
        return fig

    # ─────────── LINE ───────────
    @classmethod
    def _chart_line(cls, plt, data, title="", x_column="", y_column="",
                    y_columns=None, colors=None, show_values=False, figsize=(10, 6), **kw):
        x_column, y_column, y_columns = cls._auto_detect_columns(data, x_column, y_column, y_columns)
        labels = cls._extract_values(data, x_column)
        fig, ax = plt.subplots(figsize=figsize)

        cols_to_plot = y_columns if y_columns else [y_column]
        clrs = cls._get_colors(len(cols_to_plot), colors)

        for i, yc in enumerate(cols_to_plot):
            vals = [float(v) for v in cls._extract_values(data, yc)]
            ax.plot(range(len(vals)), vals, color=clrs[i], linewidth=2, marker='o',
                    markersize=5, label=yc, alpha=0.9)
            if show_values:
                for j, v in enumerate(vals):
                    ax.annotate(f'{v:.1f}', (j, v), textcoords="offset points",
                                xytext=(0, 8), ha='center', fontsize=8, color=DARK_THEME["text"])

        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels([str(l) for l in labels], rotation=45, ha='right')
        if len(cols_to_plot) > 1:
            ax.legend(facecolor=DARK_THEME["panel"], edgecolor=DARK_THEME["grid"])
        ax.set_title(title or "Line Chart", color=DARK_THEME["title"], fontsize=14, fontweight="bold", pad=15)
        plt.tight_layout()
        return fig

    # ─────────── PIE ───────────
    @classmethod
    def _chart_pie(cls, plt, data, title="", x_column="", y_column="",
                   colors=None, show_values=False, figsize=(8, 8), **kw):
        x_column, y_column, _ = cls._auto_detect_columns(data, x_column, y_column)
        labels = [str(l) for l in cls._extract_values(data, x_column)]
        vals = [float(v) for v in cls._extract_values(data, y_column)]
        clrs = cls._get_colors(len(vals), colors)

        fig, ax = plt.subplots(figsize=figsize)
        wedges, texts, autotexts = ax.pie(
            vals, labels=labels, colors=clrs, autopct="%1.1f%%",
            textprops={"color": DARK_THEME["text"]},
            pctdistance=0.8, startangle=90
        )
        for t in autotexts:
            t.set_fontsize(9)
            t.set_color("white")

        ax.set_title(title or "Pie Chart", color=DARK_THEME["title"], fontsize=14, fontweight="bold", pad=15)
        return fig

    # ─────────── DONUT ───────────
    @classmethod
    def _chart_donut(cls, plt, data, title="", x_column="", y_column="",
                     colors=None, figsize=(8, 8), **kw):
        x_column, y_column, _ = cls._auto_detect_columns(data, x_column, y_column)
        labels = [str(l) for l in cls._extract_values(data, x_column)]
        vals = [float(v) for v in cls._extract_values(data, y_column)]
        clrs = cls._get_colors(len(vals), colors)

        fig, ax = plt.subplots(figsize=figsize)
        wedges, texts, autotexts = ax.pie(
            vals, labels=labels, colors=clrs, autopct="%1.1f%%",
            textprops={"color": DARK_THEME["text"]},
            pctdistance=0.85, startangle=90,
            wedgeprops={"width": 0.4, "edgecolor": DARK_THEME["bg"], "linewidth": 2}
        )
        # Center circle
        centre_circle = plt.Circle((0, 0), 0.55, fc=DARK_THEME["bg"])
        ax.add_patch(centre_circle)
        # Total in center
        total = sum(vals)
        ax.text(0, 0, f"Total\n{total:,.0f}", ha='center', va='center',
                fontsize=16, fontweight='bold', color=DARK_THEME["title"])

        ax.set_title(title or "Donut Chart", color=DARK_THEME["title"], fontsize=14, fontweight="bold", pad=15)
        return fig

    # ─────────── SCATTER ───────────
    @classmethod
    def _chart_scatter(cls, plt, data, title="", x_column="", y_column="",
                       colors=None, figsize=(10, 6), **kw):
        x_column, y_column, _ = cls._auto_detect_columns(data, x_column, y_column)
        x_vals = [float(v) for v in cls._extract_values(data, x_column)]
        y_vals = [float(v) for v in cls._extract_values(data, y_column)]

        fig, ax = plt.subplots(figsize=figsize)
        clr = (colors[0] if colors else DARK_THEME["accent"])
        ax.scatter(x_vals, y_vals, color=clr, alpha=0.7, edgecolors="white", linewidth=0.5, s=60)
        ax.set_xlabel(x_column)
        ax.set_ylabel(y_column)
        ax.set_title(title or "Scatter Plot", color=DARK_THEME["title"], fontsize=14, fontweight="bold", pad=15)
        plt.tight_layout()
        return fig

    # ─────────── HISTOGRAM ───────────
    @classmethod
    def _chart_histogram(cls, plt, data, title="", x_column="", y_column="",
                         colors=None, figsize=(10, 6), **kw):
        col = y_column or x_column
        if not col:
            _, col, _ = cls._auto_detect_columns(data, "", "")
        vals = [float(v) for v in cls._extract_values(data, col)]

        fig, ax = plt.subplots(figsize=figsize)
        clr = (colors[0] if colors else DARK_THEME["accent"])
        ax.hist(vals, bins=min(30, len(vals)), color=clr, edgecolor=DARK_THEME["panel"], alpha=0.85)
        ax.set_xlabel(col)
        ax.set_ylabel("Frequency")
        ax.set_title(title or "Histogram", color=DARK_THEME["title"], fontsize=14, fontweight="bold", pad=15)
        plt.tight_layout()
        return fig

    # ─────────── HEATMAP ───────────
    @classmethod
    def _chart_heatmap(cls, plt, data, title="", x_column="", y_column="",
                       figsize=(10, 8), **kw):
        import numpy as np

        # Build matrix from data
        # Data format: [{row_label, col_label, value}, ...] or [{col1: v1, col2: v2, ...}]
        if data and isinstance(data[0], dict):
            keys = list(data[0].keys())
            if len(keys) >= 3 and all(isinstance(data[0].get(keys[2]), (int, float)) for _ in [1]):
                # Pivot format: row_label, col_label, value
                rows = sorted(set(str(d.get(keys[0], "")) for d in data))
                cols = sorted(set(str(d.get(keys[1], "")) for d in data))
                matrix = np.zeros((len(rows), len(cols)))
                for d in data:
                    ri = rows.index(str(d.get(keys[0], "")))
                    ci = cols.index(str(d.get(keys[1], "")))
                    matrix[ri][ci] = float(d.get(keys[2], 0))
            else:
                # Table format: each row is a dict of numeric values
                numeric_keys = [k for k in keys if isinstance(data[0].get(k), (int, float))]
                label_key = [k for k in keys if k not in numeric_keys]
                rows = [str(d.get(label_key[0], i)) if label_key else str(i) for i, d in enumerate(data)]
                cols = numeric_keys
                matrix = np.array([[float(d.get(c, 0)) for c in cols] for d in data])
        else:
            return None

        fig, ax = plt.subplots(figsize=figsize)
        im = ax.imshow(matrix, cmap="magma", aspect="auto")
        ax.set_xticks(range(len(cols)))
        ax.set_xticklabels(cols, rotation=45, ha='right')
        ax.set_yticks(range(len(rows)))
        ax.set_yticklabels(rows)

        # Annotate cells
        for i in range(len(rows)):
            for j in range(len(cols)):
                val = matrix[i][j]
                text_color = "white" if val < (matrix.max() + matrix.min()) / 2 else "black"
                ax.text(j, i, f'{val:.1f}', ha='center', va='center', color=text_color, fontsize=8)

        fig.colorbar(im, ax=ax, shrink=0.8)
        ax.set_title(title or "Heatmap", color=DARK_THEME["title"], fontsize=14, fontweight="bold", pad=15)
        plt.tight_layout()
        return fig

    # ─────────── RADAR ───────────
    @classmethod
    def _chart_radar(cls, plt, data, title="", x_column="", y_column="",
                     y_columns=None, colors=None, figsize=(8, 8), **kw):
        import numpy as np

        x_column, y_column, y_columns = cls._auto_detect_columns(data, x_column, y_column, y_columns)

        # Determine categories (axes) and series
        if y_columns and len(y_columns) > 1:
            categories = [str(l) for l in cls._extract_values(data, x_column)]
            series_names = y_columns
        else:
            # Single series: categories are the keys
            keys = list(data[0].keys()) if data else []
            numeric_keys = [k for k in keys if isinstance(data[0].get(k), (int, float))]
            categories = numeric_keys
            series_names = [str(data[i].get(x_column, f"Series {i}")) for i in range(len(data))]

        N = len(categories)
        angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
        angles += angles[:1]  # Close the polygon

        fig, ax = plt.subplots(figsize=figsize, subplot_kw=dict(polar=True))
        ax.set_facecolor(DARK_THEME["panel"])

        clrs = cls._get_colors(len(data) if not y_columns else len(y_columns), colors)

        if y_columns and len(y_columns) > 1:
            for i, yc in enumerate(y_columns):
                vals = [float(v) for v in cls._extract_values(data, yc)]
                vals += vals[:1]
                ax.plot(angles, vals, color=clrs[i], linewidth=2, label=yc)
                ax.fill(angles, vals, color=clrs[i], alpha=0.15)
        else:
            for i, row in enumerate(data):
                vals = [float(row.get(c, 0)) for c in categories]
                vals += vals[:1]
                label = str(row.get(x_column, f"Series {i}"))
                ax.plot(angles, vals, color=clrs[i], linewidth=2, label=label)
                ax.fill(angles, vals, color=clrs[i], alpha=0.15)

        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(categories, color=DARK_THEME["text"], fontsize=9)
        ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.1),
                  facecolor=DARK_THEME["panel"], edgecolor=DARK_THEME["grid"])
        ax.set_title(title or "Radar Chart", color=DARK_THEME["title"],
                     fontsize=14, fontweight="bold", pad=20)
        return fig

    # ─────────── WATERFALL ───────────
    @classmethod
    def _chart_waterfall(cls, plt, data, title="", x_column="", y_column="",
                         colors=None, show_values=False, figsize=(10, 6), **kw):
        import numpy as np

        x_column, y_column, _ = cls._auto_detect_columns(data, x_column, y_column)
        labels = [str(l) for l in cls._extract_values(data, x_column)]
        vals = [float(v) for v in cls._extract_values(data, y_column)]

        fig, ax = plt.subplots(figsize=figsize)

        cumulative = [0]
        for v in vals:
            cumulative.append(cumulative[-1] + v)

        color_pos = colors[0] if colors and len(colors) > 0 else "#16c79a"
        color_neg = colors[1] if colors and len(colors) > 1 else "#e94560"

        for i, v in enumerate(vals):
            bottom = cumulative[i]
            clr = color_pos if v >= 0 else color_neg
            ax.bar(labels[i], v, bottom=bottom, color=clr, edgecolor=DARK_THEME["bg"], linewidth=0.5)
            if show_values:
                ax.text(i, bottom + v / 2, f'{v:+,.0f}', ha='center', va='center',
                        color="white", fontsize=8, fontweight='bold')

        # Connection lines
        for i in range(len(vals) - 1):
            ax.plot([i + 0.4, i + 0.6], [cumulative[i + 1], cumulative[i + 1]],
                    color=DARK_THEME["grid"], linewidth=1, linestyle='--')

        ax.set_ylabel(y_column)
        plt.xticks(rotation=45, ha='right')
        ax.set_title(title or "Waterfall Chart", color=DARK_THEME["title"],
                     fontsize=14, fontweight="bold", pad=15)
        plt.tight_layout()
        return fig

    # ─────────── FUNNEL ───────────
    @classmethod
    def _chart_funnel(cls, plt, data, title="", x_column="", y_column="",
                      colors=None, figsize=(10, 6), **kw):
        x_column, y_column, _ = cls._auto_detect_columns(data, x_column, y_column)
        labels = [str(l) for l in cls._extract_values(data, x_column)]
        vals = [float(v) for v in cls._extract_values(data, y_column)]

        if not vals:
            return plt.subplots(figsize=figsize)[0]

        max_val = max(vals) if vals else 1
        clrs = cls._get_colors(len(vals), colors)

        fig, ax = plt.subplots(figsize=figsize)
        ax.set_xlim(-max_val * 0.6, max_val * 0.6)
        ax.set_ylim(-0.5, len(vals) - 0.5)
        ax.invert_yaxis()
        ax.set_axis_off()

        for i, (label, val) in enumerate(zip(labels, vals)):
            half_w = (val / max_val) * max_val * 0.5
            rect = plt.Rectangle((-half_w, i - 0.35), half_w * 2, 0.7,
                                 facecolor=clrs[i], edgecolor=DARK_THEME["bg"],
                                 linewidth=2, alpha=0.85)
            ax.add_patch(rect)
            pct = (val / max_val) * 100
            ax.text(0, i, f"{label}\n{val:,.0f} ({pct:.0f}%)", ha='center', va='center',
                    color="white", fontsize=10, fontweight='bold')

        ax.set_title(title or "Funnel Chart", color=DARK_THEME["title"],
                     fontsize=14, fontweight="bold", pad=15)
        return fig

    # ─────────── TREEMAP ───────────
    @classmethod
    def _chart_treemap(cls, plt, data, title="", x_column="", y_column="",
                       colors=None, figsize=(10, 8), **kw):
        try:
            import squarify
        except ImportError:
            # Fallback: render as horizontal bar chart
            return cls._chart_bar(plt, data, title=title or "Treemap (fallback: bar)",
                                  x_column=x_column, y_column=y_column,
                                  colors=colors, figsize=figsize)

        x_column, y_column, _ = cls._auto_detect_columns(data, x_column, y_column)
        labels = [str(l) for l in cls._extract_values(data, x_column)]
        vals = [float(v) for v in cls._extract_values(data, y_column)]
        clrs = cls._get_colors(len(vals), colors)

        fig, ax = plt.subplots(figsize=figsize)
        ax.set_axis_off()

        total = sum(vals)
        display_labels = [f"{l}\n{v:,.0f}\n({v/total*100:.1f}%)" for l, v in zip(labels, vals)]
        squarify.plot(sizes=vals, label=display_labels, color=clrs, alpha=0.85,
                      text_kwargs={"color": "white", "fontsize": 9, "fontweight": "bold"}, ax=ax)

        ax.set_title(title or "Treemap", color=DARK_THEME["title"],
                     fontsize=14, fontweight="bold", pad=15)
        return fig

    # ─────────── COMBO ───────────
    @classmethod
    def _chart_combo(cls, plt, data, title="", x_column="", y_column="",
                     y_columns=None, series=None, colors=None,
                     show_values=False, figsize=(10, 6), **kw):
        """Combo chart: mix bar + line on same axes."""
        import numpy as np

        x_column, y_column, y_columns = cls._auto_detect_columns(data, x_column, y_column, y_columns)
        labels = cls._extract_values(data, x_column)
        x_pos = np.arange(len(labels))

        fig, ax1 = plt.subplots(figsize=figsize)

        # Determine series from explicit 'series' param or auto from y_columns
        if series:
            plot_series = series
        elif y_columns and len(y_columns) > 1:
            # First column = bar, rest = line
            plot_series = [{"name": y_columns[0], "type": "bar", "y_column": y_columns[0]}]
            for yc in y_columns[1:]:
                plot_series.append({"name": yc, "type": "line", "y_column": yc})
        else:
            # Single series: just a bar chart
            plot_series = [{"name": y_column, "type": "bar", "y_column": y_column}]

        clrs = cls._get_colors(len(plot_series), colors)
        ax2 = None
        bar_count = sum(1 for s in plot_series if s.get("type", "bar") == "bar")
        bar_idx = 0

        for i, s in enumerate(plot_series):
            yc = s.get("y_column", y_column)
            vals = [float(v) for v in cls._extract_values(data, yc)]
            chart_t = s.get("type", "bar")
            name = s.get("name", yc)

            if chart_t == "bar":
                w = 0.8 / max(bar_count, 1)
                offset = bar_idx * w - (bar_count - 1) * w / 2
                ax1.bar(x_pos + offset, vals, w, label=name, color=clrs[i], alpha=0.85)
                bar_idx += 1
            elif chart_t == "line":
                if ax2 is None:
                    ax2 = ax1.twinx()
                    ax2.set_facecolor("none")
                    ax2.tick_params(colors=DARK_THEME["text"])
                ax2.plot(x_pos, vals, color=clrs[i], linewidth=2.5, marker='o',
                         markersize=6, label=name, zorder=5)

        ax1.set_xticks(x_pos)
        ax1.set_xticklabels([str(l) for l in labels], rotation=45, ha='right')

        # Combined legend
        handles1, labels1 = ax1.get_legend_handles_labels()
        handles2, labels2 = (ax2.get_legend_handles_labels() if ax2 else ([], []))
        ax1.legend(handles1 + handles2, labels1 + labels2, loc='upper left',
                   facecolor=DARK_THEME["panel"], edgecolor=DARK_THEME["grid"])

        ax1.set_title(title or "Combo Chart", color=DARK_THEME["title"],
                      fontsize=14, fontweight="bold", pad=15)
        plt.tight_layout()
        return fig
