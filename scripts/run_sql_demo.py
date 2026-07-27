"""
Load the cleaned customer CSV into a local SQLite DB and run sql/churn_analysis.sql.

Usage (from project root):
    python scripts/run_sql_demo.py
"""

from pathlib import Path
import sqlite3

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "02_clean" / "customer_churn_master.csv"
SQL_FILE = ROOT / "sql" / "churn_analysis.sql"
DB = ROOT / "sql" / "customer_churn.db"


def main() -> None:
    df = pd.read_csv(CSV)

    if DB.exists():
        DB.unlink()

    conn = sqlite3.connect(DB)
    df.to_sql("customer_churn", conn, index=False)

    raw = SQL_FILE.read_text(encoding="utf-8")
    no_line_comments = "\n".join(
        line for line in raw.splitlines() if not line.strip().startswith("--")
    )
    queries = [q.strip() for q in no_line_comments.split(";") if q.strip()]

    print(f"Loaded {len(df):,} rows into {DB.name}")
    print(f"Running {len(queries)} queries from {SQL_FILE.name}\n")

    for i, q in enumerate(queries, start=1):
        print("=" * 60)
        print(f"Query {i}")
        print("=" * 60)
        out = pd.read_sql_query(q, conn)
        print(out.to_string(index=False))
        print()

    conn.close()
    print("Done. DB kept at:", DB)


if __name__ == "__main__":
    main()
