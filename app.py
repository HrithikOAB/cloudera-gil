"""
Citizen MDM Studio — Streamlit demo
Run:  pip install -r requirements.txt && streamlit run app.py
"""
from datetime import datetime
from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st

import mdm_engine as E

st.set_page_config(page_title="Citizen MDM Studio", page_icon="🧬", layout="wide")
HERE = Path(__file__).parent
SAMPLES = [
    ("Revenue", "revenue_land_records.csv", "DD/MM/YYYY", 1),
    ("Health", "health_patients.csv", "DD/MM/YYYY", 2),
    ("Welfare", "social_welfare_beneficiaries.xlsx", "YYYY-MM-DD", 3),
    ("Municipal", "municipal_property_tax.csv", "DD/MM/YYYY", 4),
]

st.markdown(
    """
    <style>
    .block-container {padding-top: 1.6rem;}
    .mdm-hero {background:#10093A;color:#fff;padding:18px 22px;border-radius:10px;margin-bottom:12px}
    .mdm-hero b {color:#FF550D}
    .mdm-card {border:1px solid #C9CCE8;border-radius:10px;padding:12px 14px;background:#fff}
    .mdm-flag {display:inline-block;background:#FF550D;color:#fff;border-radius:10px;padding:1px 8px;font-size:12px;margin-right:4px}
    .mdm-ok {display:inline-block;background:#2E9E6A;color:#fff;border-radius:10px;padding:1px 8px;font-size:12px}
    div[data-testid="stMetricValue"] {color:#10093A}
    </style>
    """,
    unsafe_allow_html=True,
)

# ------------------------------------------------------------------ state
ss = st.session_state
ss.setdefault("sources", {})      # name -> dict(df, mapping, convention, trust, file)
ss.setdefault("decisions", {})    # pair_id -> dict(decision, steward, at, note)
ss.setdefault("reprocess_log", [])


def read_any(file_or_path, name: str) -> pd.DataFrame:
    if str(name).lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(file_or_path, dtype=str)
    return pd.read_csv(file_or_path, dtype=str, encoding="utf-8-sig")


def add_source(dept: str, df: pd.DataFrame, fname: str, convention="DD/MM/YYYY", trust=None):
    df = df.fillna("")
    ss.sources[dept] = {"df": df, "mapping": E.auto_map(df.columns), "convention": convention,
                        "trust": trust or len(ss.sources) + 1, "file": fname}


def load_samples():
    ss.sources, ss.decisions, ss.reprocess_log = {}, {}, []
    for dept, f, conv, trust in SAMPLES:
        p = HERE / "sample_data" / f
        add_source(dept, read_any(p, f), f, conv, trust)


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.markdown("### 🧬 Citizen MDM Studio")
    st.caption("Upload department files → clean → dedupe → golden record")
    c1, c2 = st.columns(2)
    if c1.button("Load sample data", use_container_width=True, type="primary"):
        load_samples()
        st.rerun()
    if c2.button("Reset", use_container_width=True):
        ss.sources, ss.decisions, ss.reprocess_log = {}, {}, []
        st.rerun()
    st.divider()
    st.markdown("**Match thresholds**")
    auto_t = st.slider("Auto-merge at or above", 0.80, 1.00, 0.92, 0.01)
    review_t = st.slider("Steward review at or above", 0.50, 0.95, 0.75, 0.01)
    st.markdown("**Attribute weights**")
    w = {
        "name": st.slider("Name", 0.0, 1.0, 0.30, 0.05),
        "dob": st.slider("Date of birth", 0.0, 1.0, 0.25, 0.05),
        "phone": st.slider("Mobile", 0.0, 1.0, 0.20, 0.05),
        "address": st.slider("Address", 0.0, 1.0, 0.25, 0.05),
    }
    total_w = sum(w.values()) or 1
    weights = {k: v / total_w for k, v in w.items()}
    st.divider()
    steward = st.text_input("Data steward (for audit trail)", "steward.sje")

st.markdown(
    "<div class='mdm-hero'><span style='font-size:22px;font-weight:700'>Citizen MDM Studio</span><br>"
    "Multilingual standardisation (English · ગુજરાતી · हिन्दी) → quality rules & quarantine → "
    "fuzzy matching → steward review → <b>golden record</b> → households</div>",
    unsafe_allow_html=True,
)

tabs = st.tabs(["📥 Sources", "🧹 Standardise", "✅ Data quality", "🚧 Quarantine", "🔗 Match & review",
                "⭐ Golden records", "🏠 Households", "🔎 Search", "📤 Export"])

# ================================================================== 1 SOURCES
with tabs[0]:
    st.subheader("Department files")
    up = st.file_uploader("Upload CSV or Excel files (one per department)", type=["csv", "xlsx", "xls"],
                          accept_multiple_files=True)
    if up:
        for f in up:
            dept = Path(f.name).stem.split("_")[0].title()
            if not any(s["file"] == f.name for s in ss.sources.values()):
                add_source(dept if dept not in ss.sources else f"{dept}{len(ss.sources) + 1}", read_any(f, f.name), f.name)
    if not ss.sources:
        st.info("Upload department files, or click **Load sample data** in the sidebar to use the 4 sample files "
                "(Revenue, Health, Welfare, Municipal).")
    for dept in list(ss.sources):
        s = ss.sources[dept]
        with st.expander(f"**{dept}** · {s['file']} · {len(s['df'])} rows", expanded=False):
            c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
            new_name = c1.text_input("Department name", dept, key=f"nm_{dept}")
            s["convention"] = c2.selectbox("Date format used by this source", E.DATE_CONVENTIONS,
                                           index=E.DATE_CONVENTIONS.index(s["convention"]), key=f"cv_{dept}")
            s["trust"] = c3.number_input("Trust rank (1 = best)", 1, 20, int(s["trust"]), key=f"tr_{dept}")
            if c4.button("Remove", key=f"rm_{dept}"):
                del ss.sources[dept]
                st.rerun()
            st.markdown("**Column mapping** (auto-detected — change if needed)")
            opts = ["—"] + list(s["df"].columns)
            cols = st.columns(5)
            for i, tgt in enumerate(E.TARGET_FIELDS):
                cur = s["mapping"].get(tgt)
                sel = cols[i % 5].selectbox(tgt, opts, index=opts.index(cur) if cur in opts else 0, key=f"map_{dept}_{tgt}")
                s["mapping"][tgt] = None if sel == "—" else sel
            st.dataframe(s["df"].head(8), use_container_width=True, hide_index=True)
            if new_name != dept and new_name and new_name not in ss.sources:
                ss.sources[new_name] = ss.sources.pop(dept)
                st.rerun()

if not ss.sources:
    st.stop()

# ------------------------------------------------------------------ run pipeline
missing_name = [d for d, s in ss.sources.items() if not s["mapping"].get("name")]
if missing_name:
    st.error(f"Map a **name** column for: {', '.join(missing_name)}")
    st.stop()

src_list = [{"name": d, "df": s["df"], "mapping": s["mapping"], "convention": s["convention"], "trust": s["trust"]}
            for d, s in ss.sources.items()]
decisions = {k: v["decision"] for k, v in ss.decisions.items()}
R = E.run_pipeline(src_list, decisions, weights, auto_t, review_t)
std, quar, pairs, gold, xwalk = R["standardised"], R["quarantine"], R["pairs"], R["golden"], R["crosswalk"]
master_of = dict(zip(xwalk["uid"], xwalk["master_id"])) if not xwalk.empty else {}
if not pairs.empty:
    pairs["same_master_now"] = [master_of.get(a) == master_of.get(b) for a, b in zip(pairs.uid_a, pairs.uid_b)]
    pairs["cluster_key"] = ["|".join(sorted((master_of.get(a, a), master_of.get(b, b)))) for a, b in zip(pairs.uid_a, pairs.uid_b)]
    open_reviews = pairs[(pairs.decision == "REVIEW") & (~pairs.pair_id.isin(ss.decisions)) & (~pairs.same_master_now)]
    pending = open_reviews.sort_values("score", ascending=False).drop_duplicates("cluster_key")
else:
    pending = pairs

# ================================================================== 2 STANDARDISE
with tabs[1]:
    m = st.columns(5)
    m[0].metric("Input records", len(std))
    m[1].metric("Passed", int((std.status == "PASS").sum()))
    m[2].metric("Quarantined", len(quar))
    m[3].metric("Golden records", len(gold))
    m[4].metric("Duplicates removed", int((std.status == "PASS").sum()) - len(gold))
    st.subheader("Original value → canonical value")
    pick = st.multiselect("Sources", list(ss.sources), default=list(ss.sources))
    view = std[std.source.isin(pick)]
    show = view[["uid", "name_original", "name_display", "name_script", "dob_original", "dob_canonical", "dob_status",
                 "phone_original", "phone_canonical", "address_original", "addr_canonical", "addr_pin", "status"]]
    st.dataframe(show, use_container_width=True, hide_index=True, height=460,
                 column_config={"name_display": "name (canonical)", "addr_canonical": "address (canonical)"})
    with st.expander("How standardisation works"):
        st.markdown(
            "- **Name**: Unicode normalise → Gujarati/Hindi transliterated to Roman → titles removed → phonetic key\n"
            "- **Mobile**: Indic digits → ASCII, strip 0 / 91 / 0091 prefixes → `+91XXXXXXXXXX` (10 digits, starts 6–9)\n"
            "- **DOB**: per-source date convention, text months, Indic digits; future / impossible / ambiguous dates flagged\n"
            "- **Address**: dictionary expansion (MG → MAHATMA GANDHI, Rd → ROAD, અમદાવાદ → AHMEDABAD) → house · street · city · PIN"
        )

# ================================================================== 3 DATA QUALITY
with tabs[2]:
    sc = R["source_scores"]
    c1, c2 = st.columns([1, 1])
    with c1:
        st.subheader("Quality score by source")
        st.bar_chart(sc.set_index("source")["avg_quality"], height=280, color="#5455F9")
        st.dataframe(sc, hide_index=True, use_container_width=True)
    with c2:
        st.subheader("Failures by rule")
        rules = R["rules"]
        piv = rules.pivot_table(index=["rule", "severity"], columns="source", values="failed", aggfunc="sum").reset_index()
        st.dataframe(piv, hide_index=True, use_container_width=True, height=390)
    st.caption("CRITICAL rules send a record to quarantine. WARNING rules keep the record but drop the bad value "
               "(e.g. an invalid mobile is not used for matching).")

# ================================================================== 4 QUARANTINE
with tabs[3]:
    st.subheader(f"Quarantine · {len(quar)} records")
    if quar.empty:
        st.success("No records in quarantine.")
    else:
        st.caption("Fix the original values below, then reprocess. Fixed records rejoin the pipeline and are matched.")
        edit = quar[["uid", "source", "quarantine_reason", "name_original", "dob_original", "phone_original", "address_original"]].copy()
        edited = st.data_editor(edit, hide_index=True, use_container_width=True, key="qedit",
                                disabled=["uid", "source", "quarantine_reason"],
                                column_config={"quarantine_reason": st.column_config.TextColumn("reason", width="medium")})
        if st.button("♻️ Reprocess fixed records", type="primary"):
            n = 0
            for (_, before), (_, after) in zip(edit.iterrows(), edited.iterrows()):
                src = ss.sources[before["source"]]
                mp, df = src["mapping"], src["df"]
                sid = before["uid"].split(":", 1)[1]
                id_col = mp.get("source_id")
                if id_col:
                    idx = df.index[df[id_col].astype(str) == sid]
                else:
                    idx = [int(sid.replace("row", "")) - 1]
                for fld, col in (("name_original", "name"), ("dob_original", "dob"), ("phone_original", "phone"), ("address_original", "address")):
                    if after[fld] != before[fld] and mp.get(col):
                        df.loc[idx, mp[col]] = after[fld]
                        n += 1
                        ss.reprocess_log.append({"at": datetime.now().strftime("%Y-%m-%d %H:%M"), "uid": before["uid"],
                                                 "field": col, "old": before[fld], "new": after[fld], "by": steward})
            st.toast(f"{n} value(s) corrected — reprocessed")
            st.rerun()
    if ss.reprocess_log:
        st.markdown("**Correction log**")
        st.dataframe(pd.DataFrame(ss.reprocess_log), hide_index=True, use_container_width=True)

# ================================================================== 5 MATCH & REVIEW
with tabs[4]:
    if pairs.empty:
        st.info("No candidate pairs found.")
    else:
        vc = pairs.decision.value_counts()
        m = st.columns(4)
        m[0].metric("Candidate pairs scored", len(pairs))
        m[1].metric("Auto-merged", int(vc.get("AUTO_MERGE", 0)))
        m[2].metric("Waiting for steward", len(pending))
        m[3].metric("Steward decisions", len(ss.decisions))

        st.subheader("Steward review queue")
        if pending.empty:
            st.success("Review queue is empty.")
        by_uid = std.set_index("uid")
        for r in pending.head(15).itertuples():
            a, b = by_uid.loc[r.uid_a], by_uid.loc[r.uid_b]
            with st.container(border=True):
                top = st.columns([3, 3, 2])
                for col, rec, uid in ((top[0], a, r.uid_a), (top[1], b, r.uid_b)):
                    col.markdown(f"**{uid}**")
                    col.markdown(f"{rec.name_original}  \n`{rec.name_display}`")
                    col.caption(f"DOB {rec.dob_canonical or '—'} · 📱 {rec.phone_canonical or '—'}  \n🏠 {rec.addr_canonical or '—'}")
                with top[2]:
                    st.markdown(f"### {r.score:.2f}")
                    st.caption(f"name {r.s_name if r.s_name == r.s_name else '–'} · dob {r.s_dob if r.s_dob == r.s_dob else '–'} · "
                               f"phone {r.s_phone if r.s_phone == r.s_phone else '–'} · addr {r.s_address if r.s_address == r.s_address else '–'}")
                    st.markdown(" ".join(f"<span class='mdm-flag'>{f}</span>" for f in r.flags.split(", ") if f), unsafe_allow_html=True)
                    b1, b2 = st.columns(2)
                    n_rel = int((open_reviews.cluster_key == r.cluster_key).sum())
                    if n_rel > 1:
                        st.caption(f"applies to {n_rel} record pairs between these two clusters")
                    for btn, label, dec in ((b1, "✅ Same person", "APPROVE"), (b2, "❌ Different", "REJECT")):
                        if btn.button(label, key=f"{dec[:2].lower()}_{r.pair_id}"):
                            for rr in open_reviews[open_reviews.cluster_key == r.cluster_key].itertuples():
                                ss.decisions[rr.pair_id] = {"decision": dec, "steward": steward,
                                                            "at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                                            "pair": f"{rr.name_a} ↔ {rr.name_b}", "score": rr.score,
                                                            "flags": rr.flags}
                            st.rerun()
        if ss.decisions:
            st.markdown("**Decision log (audit trail)**")
            log = pd.DataFrame([{"pair_id": k, **v} for k, v in ss.decisions.items()])
            st.dataframe(log, hide_index=True, use_container_width=True)
            if st.button("Undo last decision"):
                ss.decisions.pop(list(ss.decisions)[-1])
                st.rerun()

        st.subheader("All scored pairs")
        f1, f2 = st.columns([2, 3])
        dsel = f1.multiselect("Decision", ["AUTO_MERGE", "REVIEW", "NO_MATCH"], default=["AUTO_MERGE", "REVIEW"])
        q = f2.text_input("Filter by name", "")
        pv = pairs[pairs.decision.isin(dsel)]
        if q:
            pv = pv[pv.name_a.str.contains(q.upper()) | pv.name_b.str.contains(q.upper())]
        st.dataframe(pv[["name_orig_a", "name_orig_b", "dob_a", "dob_b", "s_name", "s_dob", "s_phone", "s_address", "score", "flags", "decision"]],
                     hide_index=True, use_container_width=True, height=380,
                     column_config={"score": st.column_config.ProgressColumn("score", min_value=0, max_value=1, format="%.2f")})

# ================================================================== 6 GOLDEN
with tabs[5]:
    st.subheader(f"Golden records · {len(gold)}")
    fsrc = st.slider("Show records built from at least N sources", 1, max(int(gold.source_count.max()), 1), 1)
    gv = gold[gold.source_count >= fsrc]
    st.dataframe(gv[["master_id", "name", "name_gujarati", "dob", "gender", "phone", "address", "father_or_spouse",
                     "source_count", "sources", "match_confidence", "household_id"]],
                 hide_index=True, use_container_width=True, height=360,
                 column_config={"match_confidence": st.column_config.ProgressColumn("confidence", min_value=0, max_value=1, format="%.2f")})
    st.subheader("Inspect a golden record")
    labels = [f"{r.master_id} · {r.name} ({r.source_count} sources)" for r in gold.sort_values("source_count", ascending=False).itertuples()]
    sel = st.selectbox("Golden record", labels)
    mid = sel.split(" · ")[0]
    g = gold[gold.master_id == mid].iloc[0]
    c1, c2 = st.columns([2, 3])
    with c1:
        st.markdown(f"<div class='mdm-hero'><span style='font-size:12px;color:#FF550D'>GOLDEN RECORD · {mid}</span><br>"
                    f"<span style='font-size:20px;font-weight:700'>{g['name']}</span> {g['name_gujarati']}<br>"
                    f"DOB {g['dob']} · {g['gender']}<br>📱 {g['phone']}<br>🏠 {g['address']}<br>"
                    f"<span style='font-size:12px;color:#C9CCE8'>household {g['household_id']} · confidence {g['match_confidence']:.2f}</span></div>",
                    unsafe_allow_html=True)
        st.caption("Survivorship: " + g["provenance"])
    with c2:
        st.markdown("**Contributing source records**")
        st.dataframe(xwalk[xwalk.master_id == mid].drop(columns=["master_id"]), hide_index=True, use_container_width=True)
    st.caption("Survivorship rules: name = most common spelling (Latin script preferred) · DOB = most frequent valid value · "
               "mobile = most recently updated valid number · address = most recent Latin-script address · "
               "a merge is reversible: reject the pair in the decision log.")

# ================================================================== 7 HOUSEHOLDS
with tabs[6]:
    hh = gold.groupby("household_id").agg(members=("master_id", "count"), names=("name", lambda s: ", ".join(s)),
                                          address=("address", "first")).reset_index().sort_values("members", ascending=False)
    c1, c2 = st.columns([2, 3])
    with c1:
        st.subheader(f"Households · {len(hh)}")
        st.dataframe(hh, hide_index=True, use_container_width=True, height=420)
    with c2:
        hsel = st.selectbox("Household", hh.household_id.tolist())
        mem = gold[gold.household_id == hsel]
        dot = ["graph G {", 'rankdir=LR; node [shape=box, style="rounded,filled", fontname="Arial", fontsize=11];',
               f'"{hsel}" [shape=house, fillcolor="#10093A", fontcolor="white"];']
        for r in mem.itertuples():
            dot.append(f'"{r.master_id}" [label="{r.name}\\n{r.dob}\\n{r.master_id}", fillcolor="#FFE3D6"];')
            dot.append(f'"{hsel}" -- "{r.master_id}";')
            if r.father_or_spouse:
                for o in mem.itertuples():
                    if o.name.split()[0] == r.father_or_spouse.split()[0] and o.master_id != r.master_id:
                        dot.append(f'"{o.master_id}" -- "{r.master_id}" [label="relation", color="#5455F9", fontcolor="#5455F9"];')
        dot.append("}")
        st.graphviz_chart("\n".join(dot), use_container_width=True)
        st.caption("Linked by same house + PIN with the same surname or a father/spouse reference, or same mobile + surname. "
                   "A shared mobile links a household — it never merges two people.")

# ================================================================== 8 SEARCH
with tabs[7]:
    st.subheader("Fuzzy citizen search")
    st.caption("Try: `Raahul Sharma`, `રાહુલ`, `राहुल शर्मा`, `Jignes`, `98765 43210`, `૯૮૭૬૫૪૩૨૧૦`")
    c1, c2 = st.columns([3, 1])
    qry = c1.text_input("Name (any script) or mobile", "રાહુલ શર્મા")
    th = c2.slider("Min similarity", 0.6, 1.0, 0.85, 0.01)
    if qry:
        qn = E.standardise_name(qry)
        if qn["name_canonical"]:
            st.caption(f"Query understood as **{qn['name_canonical']}** · phonetic key `{qn['name_phonetic']}`")
        res = E.search_golden(gold, qry, th)
        st.dataframe(res[["search_score", "master_id", "name", "name_gujarati", "dob", "phone", "address", "sources"]],
                     hide_index=True, use_container_width=True,
                     column_config={"search_score": st.column_config.ProgressColumn("match", min_value=0, max_value=1, format="%.2f")})

# ================================================================== 9 EXPORT
with tabs[8]:
    st.subheader("Export")
    c = st.columns(4)
    c[0].download_button("Golden records (CSV)", gold.to_csv(index=False).encode("utf-8-sig"), "golden_records.csv", "text/csv")
    c[1].download_button("Source cross-reference (CSV)", xwalk.to_csv(index=False).encode("utf-8-sig"), "crosswalk.csv", "text/csv")
    c[2].download_button("Quarantine (CSV)", quar.drop(columns=["issues"]).to_csv(index=False).encode("utf-8-sig"), "quarantine.csv", "text/csv")
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        gold.to_excel(xw, sheet_name="golden_records", index=False)
        xwalk.to_excel(xw, sheet_name="crosswalk", index=False)
        R["source_scores"].to_excel(xw, sheet_name="dq_by_source", index=False)
        R["rules"].to_excel(xw, sheet_name="dq_by_rule", index=False)
        quar.drop(columns=["issues"]).to_excel(xw, sheet_name="quarantine", index=False)
        (pairs.drop(columns=["same_master_now", "cluster_key"], errors="ignore") if not pairs.empty else pairs).to_excel(xw, sheet_name="match_pairs", index=False)
        pd.DataFrame([{"pair_id": k, **v} for k, v in ss.decisions.items()]).to_excel(xw, sheet_name="steward_decisions", index=False)
        std.drop(columns=["issues"]).to_excel(xw, sheet_name="standardised", index=False)
    c[3].download_button("Full MDM report (Excel)", buf.getvalue(), "mdm_report.xlsx",
                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")
    st.caption("On Cloudera these outputs land as Iceberg tables (golden, crosswalk, quarantine, dq_results) governed by Atlas and Ranger.")
