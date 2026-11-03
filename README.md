# Citizen MDM Studio (Streamlit demo)

A working demo that takes citizen files from several departments, cleans and standardises them (English, ગુજરાતી, हिन्दी), quarantines bad records, finds duplicates with fuzzy matching, routes doubtful matches to a data steward and builds **golden records** and **households**.

All sample data is synthetic: no real people, numbers or addresses.

## Run it

```bash
pip install -r requirements.txt
streamlit run app.py
```

Then click **Load sample data** in the sidebar, or upload your own CSV/Excel files.

## Files

| File | What it is |
|---|---|
| `app.py` | Streamlit UI (9 tabs) |
| `mdm_engine.py` | The engine: pure Python + pandas, no NLP libraries needed |
| `sample_data/` | 4 department files + `_ground_truth_people.csv` (answer key) |
| `generate_sample_data.py` | Regenerates the sample files |
| `tests/evaluate_samples.py` | Runs the pipeline on the samples and prints precision / recall |

## Sample files

| Department | File | What makes it messy |
|---|---|---|
| Revenue | `revenue_land_records.csv` | English, `DD-MM-YYYY`, "MG Rd" abbreviations, one internal duplicate |
| Health | `health_patients.csv` | ~70% Gujarati script, Gujarati digits in DOB and mobile, one future DOB, one walk-in record with no phone/address |
| Social Welfare | `social_welfare_beneficiaries.xlsx` | Hindi (Devanagari) names and addresses, spelling typos (Raahul, Jignes), `+91` numbers, one missing name, one DOB with day and month swapped |
| Municipal | `municipal_property_tax.csv` | UPPER CASE, text dates ("10 May 1985"), `0091-` / `0` prefixes, 9-digit phone, Delhi PIN, impossible date (31 Feb), an owner who moved house |

Built-in traps: a **father and son with the same name** at the same address (must NOT merge), and **families sharing one mobile** (a shared phone links a household, never merges people).

## 10-minute demo script

1. **Sources**: load the samples and open a source to show auto-detected column mapping, the per-source date convention and trust rank.
2. **Standardise**: show `રાહુલ શર્મા` → `RAHUL SHARMA`, `૯૮૭૬૫ ૪૩૨૧૦` → `+919876543210`, `10 May 1985` → `1985-05-10` and `12 MG Rd` → `12 MAHATMA GANDHI ROAD`.
3. **Data quality**: show the score by source and the failures by rule.
4. **Quarantine**: fix the future DOB (e.g. `૨૮/૦૫/૧૯૮૫`) and the missing name (`Komal Shah`), then click **Reprocess**. Both records rejoin the pipeline and get matched.
5. **Match & review**: show 113 automatic merges and 4 steward cards. Approve the day/month swap, the walk-in patient and the owner who moved. **Reject** the father/son pair. Show the decision log.
6. **Golden records**: open Rahul Sharma. Show 4 sources, the survivorship provenance and the original source records.
7. **Households**: show the family graph.
8. **Search**: type `Raahul`, `રાહુલ શર્મા` or `૯૮૭૬૫૪૩૨૧૦`.
9. **Export**: download the full Excel report.

Expected result on the samples: 118 records, 3 quarantined, 113 automatic merges, 0 false merges. After the steward decisions, 43 golden records match the 43 real people exactly.

## How matching works

- **Blocking** (so we don't compare everyone with everyone): same mobile; same phonetic surname + birth year; same phonetic first name + birth year; same DOB + initial; same PIN + phonetic first name.
- **Scores**:
  - Name: transliteration + Jaro-Winkler + phonetic key. Weight 30%.
  - DOB: exact match only, with day/month swap detected. Weight 25%.
  - Mobile: exact match on the canonical number. Weight 20%.
  - Address: compared component by component (house, street, city, PIN). Weight 25%.
  - Missing values are ignored, not counted as mismatches; the remaining weights are rescaled.
- **Decisions**:
  - Score ≥ 0.92 with no flags → auto-merge.
  - Score ≥ 0.75 → steward review.
  - These flags force a review: DOB conflict, day/month swap, low evidence, contact changed.
  - Shared phone with a different name, or a gender conflict, never merges.
- **Survivorship**:
  - Name: the most common spelling.
  - DOB: the most frequent valid date.
  - Mobile: the most recently updated valid number.
  - Address: the most recent Latin-script address.
  - Every field records which source it came from.

Thresholds and weights can be changed in the sidebar.

## Mapping to Cloudera (production)

| Demo | Cloudera |
|---|---|
| File upload | Cloudera Data Flow (NiFi) / Kafka |
| `mdm_engine.py` functions | PySpark jobs on Cloudera Data Engineering (same logic as UDFs) |
| Transliteration (built-in rules) | AI4Bharat IndicXlit for production accuracy |
| Phone parsing | Google libphonenumber |
| Golden, crosswalk, quarantine, DQ tables | Apache Iceberg tables (time travel, rollback) |
| Steward decisions | Iceberg audit table + Atlas owner/steward metadata |
| Sensitive columns | Atlas tags + Ranger masking / row filters |

## Limits of the demo

- The transliteration is rule-based. It is good for common Gujarati/Hindi names but is not a trained model.
- The address dictionary covers the sample cities. Extend `ADDRESS_DICT` and `CITIES` in `mdm_engine.py` for real data.
- Everything runs in memory, which suits up to a few tens of thousands of rows. For 50–100 M records, use the Spark version.
- Steward decisions live in the browser session; export the report to keep them.
