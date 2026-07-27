"""
Customer Churn Retention Scorecard - data build script

Reads the IBM Telco customer CSV from 01_raw, cleans it, runs EDA rollups,
trains a logistic regression churn model with full classification metrics,
scores every customer, builds a retention focus list, and writes the Excel
file used by the Power BI report.

Run from the project root:
    python scripts/build_churn_scorecard.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "01_raw"
CLEAN = ROOT / "02_clean"
OUT = ROOT / "03_outputs"
PBI_DATA = OUT / "PowerBI" / "Churn_Scorecard_Data.xlsx"
RAW_FILE = RAW / "WA_Fn-UseC_-Telco-Customer-Churn.csv"

RANDOM_STATE = 42
TEST_SIZE = 0.20


def ensure_dirs() -> None:
    CLEAN.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "PowerBI").mkdir(parents=True, exist_ok=True)
    (ROOT / "docs" / "images").mkdir(parents=True, exist_ok=True)


def load_raw() -> pd.DataFrame:
    if not RAW_FILE.exists():
        raise FileNotFoundError(
            f"Missing {RAW_FILE.name}. See 01_raw/README.md for download steps."
        )
    return pd.read_csv(RAW_FILE, dtype=str)


def clean_customers(df: pd.DataFrame) -> pd.DataFrame:
    """Clean types, fix blank TotalCharges, add analysis helpers."""
    out = df.copy()
    out.columns = [c.strip() for c in out.columns]

    out["TotalCharges"] = pd.to_numeric(out["TotalCharges"], errors="coerce")
    # Brand-new customers can have blank TotalCharges; treat as 0 for analysis.
    out["TotalCharges"] = out["TotalCharges"].fillna(0.0)

    out["MonthlyCharges"] = pd.to_numeric(out["MonthlyCharges"], errors="coerce")
    out["tenure"] = pd.to_numeric(out["tenure"], errors="coerce").fillna(0).astype(int)
    out["SeniorCitizen"] = (
        pd.to_numeric(out["SeniorCitizen"], errors="coerce").fillna(0).astype(int)
    )

    out["Churn"] = out["Churn"].astype(str).str.strip()
    out["Churn_Flag"] = (out["Churn"] == "Yes").astype(int)

    # Tenure bands for dashboard / SQL rollups
    bins = [-1, 12, 24, 48, 72, 10_000]
    labels = ["0-12", "13-24", "25-48", "49-72", "73+"]
    out["Tenure_Band"] = pd.cut(out["tenure"], bins=bins, labels=labels)

    # Simple revenue proxy for "who to save first"
    out["Estimated_Annual_Revenue"] = out["MonthlyCharges"] * 12.0

    # Human-readable senior flag
    out["SeniorCitizen_Label"] = np.where(out["SeniorCitizen"] == 1, "Yes", "No")

    return out


def segment_churn_rates(df: pd.DataFrame) -> pd.DataFrame:
    """Churn rate by key segments used in the dashboard and brief."""
    rows = []
    for col in [
        "Contract",
        "TechSupport",
        "InternetService",
        "PaymentMethod",
        "tenure_band_proxy",
    ]:
        if col == "tenure_band_proxy":
            use_col = "Tenure_Band"
        else:
            use_col = col
        g = (
            df.groupby(use_col, dropna=False)
            .agg(
                customers=("customerID", "count"),
                churners=("Churn_Flag", "sum"),
                churn_rate=("Churn_Flag", "mean"),
                avg_monthly=("MonthlyCharges", "mean"),
            )
            .reset_index()
            .rename(columns={use_col: "segment_value"})
        )
        g.insert(0, "segment", use_col)
        g["churn_rate_pct"] = (g["churn_rate"] * 100).round(1)
        g["avg_monthly"] = g["avg_monthly"].round(2)
        rows.append(g.drop(columns=["churn_rate"]))
    return pd.concat(rows, ignore_index=True)


def build_model_matrix(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, list[str]]:
    """One-hot encode categoricals for logistic regression."""
    # Estimated_Annual_Revenue is MonthlyCharges * 12 — keep it for dashboards,
    # but drop it from the model to avoid a perfect duplicate feature.
    drop_cols = [
        "Churn",
        "customerID",
        "SeniorCitizen_Label",
        "Tenure_Band",
        "Estimated_Annual_Revenue",
    ]
    model_df = df.drop(columns=drop_cols)
    y = model_df["Churn_Flag"].astype(int)
    X = model_df.drop(columns=["Churn_Flag"])
    X = pd.get_dummies(X, drop_first=True)
    feature_names = list(X.columns)
    return X, y, feature_names


def train_and_score(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, dict, pd.DataFrame, pd.DataFrame]:
    """
    Train logistic regression, attach risk scores to every customer,
    and return metrics + coefficient table + confusion matrix table.
    """
    X, y, feature_names = build_model_matrix(df)

    X_train, X_test, y_train, y_test, idx_train, idx_test = train_test_split(
        X,
        y,
        df.index,
        test_size=TEST_SIZE,
        random_state=RANDOM_STATE,
        stratify=y,
    )

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)
    X_all_s = scaler.transform(X)

    model = LogisticRegression(max_iter=2000, random_state=RANDOM_STATE)
    model.fit(X_train_s, y_train)

    y_pred = model.predict(X_test_s)
    y_prob = model.predict_proba(X_test_s)[:, 1]

    cm = confusion_matrix(y_test, y_pred)
    tn, fp, fn, tp = cm.ravel()

    metrics = {
        "n_customers": int(len(df)),
        "n_train": int(len(y_train)),
        "n_test": int(len(y_test)),
        "churn_rate_overall_pct": round(float(y.mean() * 100), 1),
        "accuracy": round(float(accuracy_score(y_test, y_pred)), 4),
        "precision": round(float(precision_score(y_test, y_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_test, y_pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y_test, y_pred, zero_division=0)), 4),
        "roc_auc": round(float(roc_auc_score(y_test, y_prob)), 4),
        "true_negatives": int(tn),
        "false_positives": int(fp),
        "false_negatives": int(fn),
        "true_positives": int(tp),
        "classification_report": classification_report(
            y_test, y_pred, target_names=["Stay", "Churn"], digits=3
        ),
    }

    # Score full population for focus-list / dashboard
    scored = df.copy()
    scored["Churn_Prob"] = model.predict_proba(X_all_s)[:, 1]
    scored["Churn_Risk_Score"] = (scored["Churn_Prob"] * 100).round(1)
    scored["Predicted_Churn"] = (scored["Churn_Prob"] >= 0.50).astype(int)

    # Coefficients (odds interpretation helpers for docs / interviews)
    coef = pd.DataFrame(
        {
            "feature": feature_names,
            "coefficient": model.coef_[0],
        }
    )
    coef["abs_coefficient"] = coef["coefficient"].abs()
    coef["direction"] = np.where(coef["coefficient"] > 0, "raises churn risk", "lowers churn risk")
    coef = coef.sort_values("abs_coefficient", ascending=False).reset_index(drop=True)
    coef["rank"] = np.arange(1, len(coef) + 1)

    cm_df = pd.DataFrame(
        {
            "label": ["True Negatives (Stay)", "False Positives", "False Negatives", "True Positives (Churn)"],
            "count": [tn, fp, fn, tp],
        }
    )

    # Keep train/test flag for transparency
    scored["Model_Split"] = "train"
    scored.loc[idx_test, "Model_Split"] = "test"

    return scored, metrics, coef, cm_df


def assign_focus_flags(df: pd.DataFrame) -> pd.DataFrame:
    """
    Two retention review buckets (Medicare-style focus list):

    1) High risk / high value
       Predicted churn probability >= 0.50 AND MonthlyCharges at/above median

    2) Elevated risk (top 20%)
       Churn_Prob in the top fifth of all customers

    Everyone else: Ok / monitor
    """
    out = df.copy()
    median_monthly = float(out["MonthlyCharges"].median())
    top20 = float(out["Churn_Prob"].quantile(0.80))

    high_value_risk = (out["Churn_Prob"] >= 0.50) & (out["MonthlyCharges"] >= median_monthly)
    elevated = out["Churn_Prob"] >= top20

    flag = np.full(len(out), "Ok / monitor", dtype=object)
    # Elevated first, then overwrite with higher-priority high-value risk
    flag[elevated] = "Elevated risk (top 20%)"
    flag[high_value_risk] = "High risk / high value"

    out["Focus_Flag"] = flag
    out["Focus_Priority"] = np.select(
        [
            out["Focus_Flag"] == "High risk / high value",
            out["Focus_Flag"] == "Elevated risk (top 20%)",
        ],
        [1, 2],
        default=3,
    )
    out.attrs["median_monthly"] = median_monthly
    out.attrs["top20_threshold"] = top20
    return out


def kpi_summary(df: pd.DataFrame, metrics: dict) -> pd.DataFrame:
    focus = df[df["Focus_Flag"] != "Ok / monitor"]
    high_val = df[df["Focus_Flag"] == "High risk / high value"]
    elevated = df[df["Focus_Flag"] == "Elevated risk (top 20%)"]

    rows = [
        ("customers_in_roster", len(df)),
        ("churners_actual", int(df["Churn_Flag"].sum())),
        ("churn_rate_pct", round(float(df["Churn_Flag"].mean() * 100), 1)),
        ("avg_monthly_charges", round(float(df["MonthlyCharges"].mean()), 2)),
        ("median_monthly_charges", round(float(df["MonthlyCharges"].median()), 2)),
        ("model_accuracy", metrics["accuracy"]),
        ("model_precision", metrics["precision"]),
        ("model_recall", metrics["recall"]),
        ("model_f1", metrics["f1"]),
        ("model_roc_auc", metrics["roc_auc"]),
        ("focus_list_customers", len(focus)),
        ("high_risk_high_value", len(high_val)),
        ("elevated_risk_top20_only", len(elevated)),
        ("focus_est_annual_revenue_at_risk", round(float(focus["Estimated_Annual_Revenue"].sum()), 0)),
    ]
    return pd.DataFrame(rows, columns=["metric", "value"])


def write_outputs(
    scored: pd.DataFrame,
    segments: pd.DataFrame,
    metrics: dict,
    coef: pd.DataFrame,
    cm_df: pd.DataFrame,
    kpis: pd.DataFrame,
) -> None:
    # Clean master table for SQL / sharing
    master_cols = [
        "customerID",
        "gender",
        "SeniorCitizen",
        "SeniorCitizen_Label",
        "Partner",
        "Dependents",
        "tenure",
        "Tenure_Band",
        "PhoneService",
        "MultipleLines",
        "InternetService",
        "OnlineSecurity",
        "OnlineBackup",
        "DeviceProtection",
        "TechSupport",
        "StreamingTV",
        "StreamingMovies",
        "Contract",
        "PaperlessBilling",
        "PaymentMethod",
        "MonthlyCharges",
        "TotalCharges",
        "Estimated_Annual_Revenue",
        "Churn",
        "Churn_Flag",
        "Churn_Prob",
        "Churn_Risk_Score",
        "Predicted_Churn",
        "Focus_Flag",
        "Focus_Priority",
        "Model_Split",
    ]
    master = scored[master_cols].copy()
    master_path = CLEAN / "customer_churn_master.csv"
    master.to_csv(master_path, index=False)

    focus = master[master["Focus_Flag"] != "Ok / monitor"].sort_values(
        ["Focus_Priority", "Churn_Prob", "MonthlyCharges"],
        ascending=[True, False, False],
    )
    focus_path = OUT / "focus_customers.csv"
    focus.to_csv(focus_path, index=False)

    segments.to_csv(OUT / "segment_churn_rates.csv", index=False)
    coef.to_csv(OUT / "model_coefficients.csv", index=False)
    cm_df.to_csv(OUT / "confusion_matrix.csv", index=False)
    kpis.to_csv(OUT / "kpi_summary.csv", index=False)

    metrics_path = OUT / "model_metrics.json"
    metrics_out = {k: v for k, v in metrics.items() if k != "classification_report"}
    metrics_path.write_text(json.dumps(metrics_out, indent=2), encoding="utf-8")
    (OUT / "classification_report.txt").write_text(
        metrics["classification_report"], encoding="utf-8"
    )

    # Power BI workbook (multiple sheets, like Medicare Scorecard_Data.xlsx)
    with pd.ExcelWriter(PBI_DATA, engine="openpyxl") as writer:
        master.to_excel(writer, sheet_name="customers", index=False)
        focus.to_excel(writer, sheet_name="focus_list", index=False)
        segments.to_excel(writer, sheet_name="segment_rates", index=False)
        kpis.to_excel(writer, sheet_name="kpis", index=False)
        coef.head(25).to_excel(writer, sheet_name="top_drivers", index=False)
        cm_df.to_excel(writer, sheet_name="confusion_matrix", index=False)

    print(f"Wrote {master_path.relative_to(ROOT)} ({len(master):,} rows)")
    print(f"Wrote {focus_path.relative_to(ROOT)} ({len(focus):,} focus customers)")
    print(f"Wrote {PBI_DATA.relative_to(ROOT)}")
    print(f"Wrote {metrics_path.relative_to(ROOT)}")


def print_summary(kpis: pd.DataFrame, metrics: dict, scored: pd.DataFrame) -> None:
    print("\n=== Quick totals ===")
    for _, row in kpis.iterrows():
        print(f"  {row['metric']}: {row['value']}")
    print("\n=== Test-set model metrics ===")
    print(f"  Accuracy : {metrics['accuracy']:.1%}")
    print(f"  Precision: {metrics['precision']:.1%}")
    print(f"  Recall   : {metrics['recall']:.1%}")
    print(f"  F1       : {metrics['f1']:.1%}")
    print(f"  ROC-AUC  : {metrics['roc_auc']:.3f}")
    print("\n=== Focus list mix ===")
    print(scored["Focus_Flag"].value_counts().to_string())
    print("\n=== Classification report (test) ===")
    print(metrics["classification_report"])


def main() -> None:
    ensure_dirs()
    raw = load_raw()
    clean = clean_customers(raw)
    segments = segment_churn_rates(clean)
    scored, metrics, coef, cm_df = train_and_score(clean)
    scored = assign_focus_flags(scored)
    kpis = kpi_summary(scored, metrics)
    write_outputs(scored, segments, metrics, coef, cm_df, kpis)
    print_summary(kpis, metrics, scored)
    print("Done. Open 03_outputs/PowerBI/Churn_Scorecard_Data.xlsx in Power BI and refresh.")


if __name__ == "__main__":
    main()
