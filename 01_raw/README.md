# Raw Telco files

Download the IBM Telco Customer Churn CSV (same file used in this project):

https://raw.githubusercontent.com/IBM/telco-customer-churn-on-icp4d/master/data/Telco-Customer-Churn.csv

Save it in this folder as:

```
WA_Fn-UseC_-Telco-Customer-Churn.csv
```

After downloading, rebuild the clean tables and model outputs with:

```bash
python scripts/build_churn_scorecard.py
```

The cleaned master CSV and Power BI Excel workbook are written under `02_clean/` and `03_outputs/`.
