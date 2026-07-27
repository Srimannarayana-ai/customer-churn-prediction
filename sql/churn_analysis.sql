-- Customer Churn Retention Scorecard - SQL analysis
-- Run via: python scripts/run_sql_demo.py
-- Assumes table customer_churn already loaded (see that script).

-- 1) Roster vs actual churners
SELECT
    COUNT(*) AS customers_in_roster,
    SUM(Churn_Flag) AS actual_churners,
    ROUND(100.0 * SUM(Churn_Flag) / COUNT(*), 1) AS churn_rate_pct,
    ROUND(AVG(MonthlyCharges), 2) AS avg_monthly,
    ROUND(AVG(Churn_Risk_Score), 1) AS avg_risk_score
FROM customer_churn;


-- 2) Churn rate by contract type
SELECT
    Contract,
    COUNT(*) AS customers,
    SUM(Churn_Flag) AS churners,
    ROUND(100.0 * SUM(Churn_Flag) / COUNT(*), 1) AS churn_rate_pct,
    ROUND(AVG(MonthlyCharges), 2) AS avg_monthly,
    ROUND(AVG(Churn_Risk_Score), 1) AS avg_risk_score
FROM customer_churn
GROUP BY Contract
ORDER BY churn_rate_pct DESC;


-- 3) Churn rate by Tech Support (classic driver)
SELECT
    TechSupport,
    COUNT(*) AS customers,
    SUM(Churn_Flag) AS churners,
    ROUND(100.0 * SUM(Churn_Flag) / COUNT(*), 1) AS churn_rate_pct,
    ROUND(AVG(Churn_Risk_Score), 1) AS avg_risk_score
FROM customer_churn
GROUP BY TechSupport
ORDER BY churn_rate_pct DESC;


-- 4) Focus list mix and revenue at risk
SELECT
    Focus_Flag,
    COUNT(*) AS customers,
    SUM(Churn_Flag) AS already_churned,
    ROUND(AVG(Churn_Prob), 3) AS avg_churn_prob,
    ROUND(AVG(MonthlyCharges), 2) AS avg_monthly,
    ROUND(SUM(Estimated_Annual_Revenue), 0) AS est_annual_revenue
FROM customer_churn
GROUP BY Focus_Flag
ORDER BY
    CASE Focus_Flag
        WHEN 'High risk / high value' THEN 1
        WHEN 'Elevated risk (top 20%)' THEN 2
        ELSE 3
    END;


-- 5) Within each contract, top 5 highest-risk customers still tagged for review
--    (window function) — useful for a call-list style handoff
WITH ranked AS (
    SELECT
        Contract,
        customerID,
        TechSupport,
        InternetService,
        tenure,
        MonthlyCharges,
        Churn_Risk_Score,
        Focus_Flag,
        Churn,
        ROW_NUMBER() OVER (
            PARTITION BY Contract
            ORDER BY Churn_Prob DESC, MonthlyCharges DESC
        ) AS risk_rank_in_contract
    FROM customer_churn
    WHERE Focus_Flag != 'Ok / monitor'
)
SELECT *
FROM ranked
WHERE risk_rank_in_contract <= 5
ORDER BY Contract, risk_rank_in_contract;


-- 6) Tenure band risk (who leaves early vs late)
SELECT
    Tenure_Band,
    COUNT(*) AS customers,
    SUM(Churn_Flag) AS churners,
    ROUND(100.0 * SUM(Churn_Flag) / COUNT(*), 1) AS churn_rate_pct,
    ROUND(AVG(Churn_Risk_Score), 1) AS avg_risk_score
FROM customer_churn
GROUP BY Tenure_Band
ORDER BY
    CASE Tenure_Band
        WHEN '0-12' THEN 1
        WHEN '13-24' THEN 2
        WHEN '25-48' THEN 3
        WHEN '49-72' THEN 4
        ELSE 5
    END;
