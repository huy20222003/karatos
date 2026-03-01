import asyncio
import os
import json
import sys

# Add root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.file_reader import FileReader
from tools.data_analyzer import DataAnalyzer

async def verify_migration():
    print("--- Verifying pandas to polars migration ---")
    
    # 1. Create a dummy CSV file
    csv_path = "test_data.csv"
    with open(csv_path, "w") as f:
        f.write("name,age,city\nAlice,30,New York\nBob,25,Los Angeles\nCharlie,35,Chicago\n")
    
    try:
        # 2. Test FileReader with CSV
        print("\nTesting FileReader.read with CSV...")
        fr_result = await FileReader.execute(file_path=csv_path)
        if fr_result["status"] == "success":
            print("FileReader SUCCESS")
            print("Content preview:")
            print(fr_result["data"]["content"][:200])
        else:
            print(f"FileReader FAILED: {fr_result['message']}")
            return

        # 3. Test DataAnalyzer with data array
        print("\nTesting DataAnalyzer.analyze_data (summary)...")
        data = [
            {"name": "Alice", "age": 30, "score": 85},
            {"name": "Bob", "age": 25, "score": 90},
            {"name": "Charlie", "age": 35, "score": 75}
        ]
        da_result = await DataAnalyzer.execute(data=data, analysis_type="summary")
        if da_result["status"] == "success":
            print("DataAnalyzer Summary SUCCESS")
            print(json.dumps(da_result["data"]["shape"], indent=2))
            print("Numeric summary ages mean:", da_result["data"]["numeric_summary"]["age"]["mean"])
        else:
            print(f"DataAnalyzer Summary FAILED: {da_result['message']}")
            return

        # 4. Test DataAnalyzer Correlation
        print("\nTesting DataAnalyzer.analyze_data (correlation)...")
        da_corr = await DataAnalyzer.execute(data=data, analysis_type="correlation")
        if da_corr["status"] == "success":
            print("DataAnalyzer Correlation SUCCESS")
            # print(json.dumps(da_corr["data"], indent=2))
        else:
            print(f"DataAnalyzer Correlation FAILED: {da_corr['message']}")
            return

        # 5. Test DataAnalyzer Chart
        print("\nTesting DataAnalyzer.analyze_data (chart)...")
        da_chart = await DataAnalyzer.execute(data=data, analysis_type="chart", chart_type="bar", x_column="name", y_column="age")
        if da_chart["status"] == "success":
            print(f"DataAnalyzer Chart SUCCESS: {da_chart['data']['chart_path']}")
        else:
            print(f"DataAnalyzer Chart FAILED: {da_chart['message']}")
            return

        print("\n--- ALL TESTS PASSED ---")

    finally:
        # Cleanup
        if os.path.exists(csv_path):
            os.remove(csv_path)

if __name__ == "__main__":
    asyncio.run(verify_migration())
