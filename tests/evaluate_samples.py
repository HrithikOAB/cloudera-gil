import re, sys
from datetime import date
import pandas as pd
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
from mdm_engine import auto_map, run_pipeline

D = str(__import__("pathlib").Path(__file__).resolve().parents[1] / "sample_data") + "/"
cfg = [("Revenue", "revenue_land_records.csv", "DD/MM/YYYY", 1), ("Health", "health_patients.csv", "DD/MM/YYYY", 2),
       ("Welfare", "social_welfare_beneficiaries.xlsx", "YYYY-MM-DD", 3), ("Municipal", "municipal_property_tax.csv", "DD/MM/YYYY", 4)]
sources = []
for name, f, conv, t in cfg:
    df = pd.read_excel(D + f, dtype=str) if f.endswith("xlsx") else pd.read_csv(D + f, dtype=str)
    m = auto_map(df.columns)
    print(name, {k: v for k, v in m.items() if v})
    sources.append({"name": name, "df": df, "mapping": m, "convention": conv, "trust": t})
res = run_pipeline(sources, today=date(2026, 11, 3))
std, pairs, g, x = res["standardised"], res["pairs"], res["golden"], res["crosswalk"]
print("\nrecords", len(std), "quarantine", len(res["quarantine"]))
print(res["quarantine"][["uid", "name_original", "dob_original", "quarantine_reason"]].to_string())
print(res["source_scores"].to_string())
print(pairs["decision"].value_counts().to_dict())
rev = pd.read_csv(D + "revenue_land_records.csv", dtype=str)
def pid(uid):
    src, sid = uid.split(":", 1)
    if sid == "REV9001":
        return int(rev.iloc[3]["land_rec_id"][3:]) - 1000
    return int(re.sub(r"\D", "", sid)) % 1000
x["pid"] = x["uid"].apply(pid)
# precision / recall over record pairs
from itertools import combinations
pred = set(); true = set()
for _, grp in x.groupby("master_id"):
    pred |= {tuple(sorted(c)) for c in combinations(grp["uid"], 2)}
for _, grp in x.groupby("pid"):
    true |= {tuple(sorted(c)) for c in combinations(grp["uid"], 2)}
tp = len(pred & true)
print(f"\ngolden={len(g)} true_people_in_passed={x['pid'].nunique()}  pairs: TP={tp} FP={len(pred-true)} FN={len(true-pred)}")
print("precision", round(tp / max(len(pred), 1), 3), "recall", round(tp / max(len(true), 1), 3))
review = pairs[pairs.decision == "REVIEW"]
review = review.assign(same=[pid(a) == pid(b) for a, b in zip(review.uid_a, review.uid_b)])
print("\nREVIEW queue:\n", review[["name_orig_a", "name_orig_b", "dob_a", "dob_b", "score", "flags", "same"]].to_string())
fn = true - pred
for a, b in list(fn)[:15]:
    r = pairs[((pairs.uid_a == a) & (pairs.uid_b == b)) | ((pairs.uid_a == b) & (pairs.uid_b == a))]
    print("FN", a, b, r[["score", "s_name", "s_dob", "s_phone", "s_address", "flags", "decision"]].values.tolist() if len(r) else "NOT BLOCKED")
for a, b in list(pred - true)[:10]:
    print("FP", a, b)
print(g[["master_id", "name", "name_gujarati", "dob", "phone", "address", "sources", "household_id", "household_size"]].head(12).to_string())
print("households:", g["household_id"].nunique())
