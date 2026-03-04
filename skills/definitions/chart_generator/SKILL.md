---
name: "chart_generator"
enabled: true
version: "1.0.0"
author: "Karatos Core"

description: >
  Professional Chart & Graph Engine. Generates publication-quality data visualizations
  from structured data. Supports 12+ chart types with a modern dark theme.
  
  USE WHEN:
  - User asks to visualize, plot, graph, or chart any data
  - User wants a comparison, distribution, or composition visualization
  - User asks "vẽ biểu đồ", "tạo đồ thị", "show me a chart"
  - Data needs to be presented visually for better understanding
  
  DO NOT USE WHEN:
  - User just wants raw numbers or statistics (use data_analyzer instead)
  - User wants to analyze correlations without visualization

routing_examples:
  - '"Vẽ biểu đồ cột cho doanh thu theo tháng" -> PLAN (chart generation with bar type)'
  - '"Draw a pie chart showing market share" -> PLAN (pie chart visualization)'
  - '"Show me a radar chart comparing product features" -> PLAN (radar chart)'
  - '"Tạo biểu đồ kết hợp cột và đường" -> PLAN (combo chart: bar + line)'
  - '"Heatmap of correlation between variables" -> PLAN (heatmap generation)'
  - '"Vẽ biểu đồ donut cho cơ cấu chi phí" -> PLAN (donut chart)'
  - '"Create a funnel chart for conversion rates" -> PLAN (funnel chart)'
  - '"Waterfall chart of profit and loss" -> PLAN (waterfall chart)'

inputs:
  chart_type:
    type: string
    required: true
    description: >
      Type of chart. One of: bar, line, pie, donut, heatmap, radar, scatter,
      histogram, waterfall, funnel, treemap, combo.
    examples:
      - "bar"
      - "combo"
      - "heatmap"
  
  data:
    type: array
    required: true
    description: >
      Array of data objects. Each object is a row with named fields.
      Example: [{"month": "Jan", "revenue": 100}, {"month": "Feb", "revenue": 150}]
  
  title:
    type: string
    required: false
    description: "Chart title displayed at the top."
  
  x_column:
    type: string
    required: false
    description: "Column name for X axis / labels. Auto-detected if not provided."
  
  y_column:
    type: string
    required: false
    description: "Column name for Y axis / values. Auto-detected if not provided."
  
  y_columns:
    type: array
    required: false
    description: "Multiple Y columns for multi-series or combo charts."
  
  series:
    type: array
    required: false
    description: >
      For combo charts: array of {name, type, y_column} defining each series.
      Example: [{"name": "Revenue", "type": "bar", "y_column": "revenue"},
                {"name": "Growth %", "type": "line", "y_column": "growth"}]

outputs:
  success:
    type: object
    schema:
      status: { type: string, value: "success" }
      photo: { type: bytes, description: "PNG image bytes for direct Telegram sending." }
      data: { type: object, description: "Contains chart_path for the saved file." }
  error:
    type: object
    schema:
      status: { type: string, value: "error" }
      message: { type: string }

required_capabilities:
  - "computation: matplotlib and numpy for chart rendering"

tags:
  - "data"
  - "visualization"
  - "chart"
---

# Skill: Chart Generator

You are the Visualization Engine responsible for generating professional data charts and graphs.

## Context Awareness

Before generating a chart:
- **Data shape**: Inspect the data array to determine what columns are available.
- **Auto-detection**: If `x_column` or `y_column` are not specified, detect the best columns automatically
  (label/string columns for X, numeric columns for Y).
- **Chart selection**: If the user doesn't specify a chart type, choose the most appropriate one
  based on the data structure and user intent.

## Procedure

### Step 1: Validate Input
- Ensure `data` is a non-empty array of objects.
- Validate `chart_type` is one of the 12 supported types.
- Auto-detect columns if not explicitly provided.

### Step 2: Generate Chart
- Apply the dark professional theme automatically.
- Use appropriate color palette for the data series count.
- Handle edge cases: empty values, missing columns, single-row data.

### Step 3: Return Result
- Return both `photo` (bytes) for immediate Telegram display and `chart_path` for file reference.
- If generation fails, return a clear error with recovery hint.

## Chart Type Selection Guide

| Data Pattern | Recommended Chart |
|-------------|------------------|
| Categories vs values | bar |
| Time series | line |
| Composition / proportions | pie or donut |
| Multi-dimensional comparison | radar |
| Matrix / correlation | heatmap |
| Sequential gains/losses | waterfall |
| Stage-based conversion | funnel |
| Hierarchical proportions | treemap |
| Two metrics on one axis | combo |

## Constraints

- Maximum 1000 data points per chart for readability.
- Treemap requires the `squarify` package (falls back to bar if unavailable).
- All charts use PNG format at 150 DPI.
