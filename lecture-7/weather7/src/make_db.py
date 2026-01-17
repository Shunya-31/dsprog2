import sqlite3
import pandas as pd
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent

CSV_PATH = SRC_DIR / "output" / "ski_resorts.csv"
DB_PATH  = SRC_DIR / "output" / "ski.db"

TABLE_NAME = "ski_resorts"

def main():
    print("CSV_PATH =", CSV_PATH)
    print("DB_PATH  =", DB_PATH)

    df = pd.read_csv(CSV_PATH)

    conn = sqlite3.connect(DB_PATH)
    df.to_sql(TABLE_NAME, conn, if_exists="replace", index=False)
    conn.close()

    print(f"DB作成完了: {DB_PATH} / 行数: {len(df)}")

if __name__ == "__main__":
    main()

