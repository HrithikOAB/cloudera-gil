"""
Citizen MDM engine (demo)
-------------------------
Pure Python + pandas. No external NLP libraries, so it runs anywhere.

Pipeline:
    load sources -> map columns -> standardise (name, DOB, phone, address)
    -> data-quality rules (critical => quarantine, warning => flag)
    -> blocking -> pairwise scoring -> decision (auto / review / no match)
    -> clustering (auto + steward-approved) -> survivorship -> golden records
    -> household linking

Production note: the same logic maps 1:1 to PySpark on Cloudera Data Engineering;
transliteration can be swapped for AI4Bharat IndicXlit and phone parsing for
Google libphonenumber.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from datetime import date, datetime

import pandas as pd

# =====================================================================
# 1. Script helpers
# =====================================================================
GUJ_START, GUJ_END = 0x0A80, 0x0AFF
DEV_START, DEV_END = 0x0900, 0x097F
GUJ_TO_DEV_OFFSET = 0x0A80 - 0x0900  # Indic blocks share one layout


def detect_script(text) -> str:
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return "NONE"
    counts = Counter()
    for ch in str(text):
        cp = ord(ch)
        if GUJ_START <= cp <= GUJ_END:
            counts["GUJARATI"] += 1
        elif DEV_START <= cp <= DEV_END:
            counts["DEVANAGARI"] += 1
        elif ch.isalpha():
            counts["LATIN"] += 1
    if not counts:
        return "NONE"
    return counts.most_common(1)[0][0]


def to_ascii_digits(value) -> str:
    """૯૮૭ / ९८७ -> 987 (any Unicode decimal digit)."""
    if value is None:
        return ""
    out = []
    for ch in str(value):
        if ch.isdigit():
            try:
                out.append(str(unicodedata.digit(ch)))
                continue
            except (TypeError, ValueError):
                pass
        out.append(ch)
    return "".join(out)


# --- Devanagari -> Roman (Gujarati is shifted onto Devanagari first) ---
_VOWELS = {"अ": "a", "आ": "aa", "इ": "i", "ई": "ii", "उ": "u", "ऊ": "uu", "ऋ": "ri", "ए": "e", "ऐ": "ai",
           "ओ": "o", "औ": "au", "ऍ": "e", "ऑ": "o", "ऎ": "e", "ऒ": "o"}
_MATRAS = {"ा": "aa", "ि": "i", "ी": "ii", "ु": "u", "ू": "uu", "ृ": "ri", "े": "e", "ै": "ai", "ो": "o",
           "ौ": "au", "ॅ": "e", "ॉ": "o", "ॆ": "e", "ॊ": "o"}
_CONS = {"क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n", "च": "ch", "छ": "chh", "ज": "j", "झ": "jh",
         "ञ": "n", "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n", "त": "t", "थ": "th", "द": "d",
         "ध": "dh", "न": "n", "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m", "य": "y", "र": "r",
         "ल": "l", "ळ": "l", "व": "v", "श": "sh", "ष": "sh", "स": "s", "ह": "h"}
_VIRAMA, _ANUSVARA, _CHANDRA, _VISARGA, _NUKTA = "्", "ं", "ँ", "ः", "़"
_SCHWA = "@"  # internal marker for the inherent vowel


def _to_devanagari(text: str) -> str:
    out = []
    for ch in text:
        cp = ord(ch)
        if GUJ_START <= cp <= GUJ_END:
            out.append(chr(cp - GUJ_TO_DEV_OFFSET))
        else:
            out.append(ch)
    return "".join(out)


def _translit_word(word: str) -> str:
    """Return a list of units: consonant strings, vowels, and '@' for inherent schwa."""
    units = []  # (kind, text) kind in C,V,@
    i = 0
    while i < len(word):
        ch = word[i]
        if ch in _CONS:
            units.append(("C", _CONS[ch]))
            nxt = word[i + 1] if i + 1 < len(word) else ""
            if nxt == _NUKTA:
                i += 1
                nxt = word[i + 1] if i + 1 < len(word) else ""
            if nxt in _MATRAS:
                units.append(("V", _MATRAS[nxt]))
                i += 1
            elif nxt == _VIRAMA:
                i += 1
            else:
                units.append(("@", "a"))
        elif ch in _VOWELS:
            units.append(("V", _VOWELS[ch]))
        elif ch in (_ANUSVARA, _CHANDRA):
            units.append(("C", "n"))
        elif ch == _VISARGA:
            units.append(("C", "h"))
        elif ch in _MATRAS:  # stray matra
            units.append(("V", _MATRAS[ch]))
        elif ch == _NUKTA:
            pass
        else:
            units.append(("X", ch))
        i += 1
    # schwa deletion: word-final, then medial V C @ C V (right to left)
    if len(units) > 2 and units[-1][0] == "@":
        units.pop()
    for k in range(len(units) - 3, 1, -1):
        if units[k][0] != "@":
            continue
        prev_c = units[k - 1][0] == "C"
        prev_v = units[k - 2][0] in ("V", "@")
        next_c = k + 1 < len(units) and units[k + 1][0] == "C"
        next_v = k + 2 < len(units) and units[k + 2][0] in ("V", "@")
        if prev_c and prev_v and next_c and next_v:
            units.pop(k)
    return "".join(u[1] for u in units)


def transliterate(text) -> str:
    """Gujarati / Devanagari / Latin -> Roman (lower case, best effort)."""
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return ""
    text = unicodedata.normalize("NFC", str(text))
    text = _to_devanagari(text)
    if not any(DEV_START <= ord(c) <= DEV_END for c in text):
        return text
    parts = re.split(r"(\s+|[,./\-()]+)", text)
    return "".join(_translit_word(p) if any(DEV_START <= ord(c) <= DEV_END for c in p) else p for p in parts)


def roman_upper(text: str, collapse: str = "all") -> str:
    """Upper-case Roman text. collapse='all' merges long vowels (AA/II/UU/EE/OO) for matching keys,
    'indic' merges only AA/II/UU (transliteration artefacts), 'none' keeps spelling."""
    t = to_ascii_digits(text)
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.upper()
    pairs = {"all": (("AA", "A"), ("II", "I"), ("UU", "U"), ("EE", "I"), ("OO", "U")),
             "indic": (("AA", "A"), ("II", "I"), ("UU", "U")), "none": ()}[collapse]
    for a, b in pairs:
        t = t.replace(a, b)
    return t


# =====================================================================
# 2. Name intelligence
# =====================================================================
_NAME_NOISE = re.compile(r"[^A-Z\s]")
_TITLES = {"MR", "MRS", "MS", "SHRI", "SMT", "KUM", "DR", "SHREE", "SHRIMATI", "KUMARI"}


def standardise_name(raw) -> dict:
    script = detect_script(raw)
    if script == "NONE":
        return {"name_canonical": "", "name_display": "", "name_script": "NONE", "name_phonetic": ""}
    tr = transliterate(raw)
    t = _NAME_NOISE.sub(" ", roman_upper(tr))
    tokens = [x for x in t.split() if x and x not in _TITLES]
    disp = _NAME_NOISE.sub(" ", roman_upper(tr, "none" if script == "LATIN" else "indic"))
    disp = " ".join(x for x in disp.split() if x not in _TITLES)
    return {"name_canonical": " ".join(tokens), "name_display": disp, "name_script": script,
            "name_phonetic": " ".join(phonetic(x) for x in tokens)}


def phonetic(token: str) -> str:
    """Indian-name friendly consonant skeleton: RAHUL/RAAHUL -> RL, MEHTA/MAHETA -> MT."""
    if not token:
        return ""
    t = token.upper()
    for a, b in (("CHH", "C"), ("CH", "C"), ("SH", "S"), ("PH", "F"), ("BH", "B"), ("KH", "K"), ("GH", "G"),
                 ("JH", "J"), ("TH", "T"), ("DH", "D"), ("CK", "K"), ("Q", "K"), ("Z", "J"), ("W", "V"),
                 ("X", "KS"), ("Y", "I")):
        t = t.replace(a, b)
    first = t[0]
    rest = "".join(c for c in t[1:] if c not in "AEIOUH")
    key = first + rest
    out = []
    for c in key:
        if not out or out[-1] != c:
            out.append(c)
    return "".join(out)


# =====================================================================
# 3. Similarity (Jaro-Winkler, token set) - pure python
# =====================================================================
def jaro_winkler(s1: str, s2: str, p: float = 0.1) -> float:
    if not s1 or not s2:
        return 0.0
    if s1 == s2:
        return 1.0
    l1, l2 = len(s1), len(s2)
    window = max(l1, l2) // 2 - 1
    m1, m2 = [False] * l1, [False] * l2
    matches = 0
    for i, c in enumerate(s1):
        lo, hi = max(0, i - window), min(i + window + 1, l2)
        for j in range(lo, hi):
            if not m2[j] and s2[j] == c:
                m1[i] = m2[j] = True
                matches += 1
                break
    if matches == 0:
        return 0.0
    t, k = 0, 0
    for i in range(l1):
        if m1[i]:
            while not m2[k]:
                k += 1
            if s1[i] != s2[k]:
                t += 1
            k += 1
    t /= 2
    jaro = (matches / l1 + matches / l2 + (matches - t) / matches) / 3
    prefix = 0
    for a, b in zip(s1[:4], s2[:4]):
        if a != b:
            break
        prefix += 1
    return jaro + prefix * p * (1 - jaro)


def token_similarity(a: str, b: str) -> float:
    ta, tb = a.split(), b.split()
    if not ta or not tb:
        return 0.0
    if len(ta) > len(tb):
        ta, tb = tb, ta
    return sum(max(jaro_winkler(x, y) for y in tb) for x in ta) / len(ta)


def name_similarity(a: dict, b: dict) -> float:
    if not a["name_canonical"] or not b["name_canonical"]:
        return None
    sim = max(jaro_winkler(a["name_canonical"], b["name_canonical"]), token_similarity(a["name_canonical"], b["name_canonical"]))
    pa, pb = set(a["name_phonetic"].split()), set(b["name_phonetic"].split())
    if pa and pa == pb and sim >= 0.8 and min(len(x) for x in pa) >= 2:
        sim = max(sim, 0.97)
    return round(min(sim, 1.0), 4)


# =====================================================================
# 4. Phone intelligence
# =====================================================================
def standardise_phone(raw) -> dict:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)) or str(raw).strip() == "":
        return {"phone_canonical": "", "phone_status": "MISSING"}
    s = to_ascii_digits(raw)
    if isinstance(raw, float):
        s = str(int(raw))
    digits = re.sub(r"\D", "", s)
    if digits.startswith("0091"):
        digits = digits[4:]
    elif digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    if len(digits) == 10 and digits[0] in "6789":
        return {"phone_canonical": "+91" + digits, "phone_status": "VALID"}
    return {"phone_canonical": "", "phone_status": "INVALID"}


# =====================================================================
# 5. DOB intelligence
# =====================================================================
_MONTHS = {m: i for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}
DATE_CONVENTIONS = ["DD/MM/YYYY", "MM/DD/YYYY", "YYYY-MM-DD", "AUTO (flag ambiguous)"]


def standardise_dob(raw, convention: str = "DD/MM/YYYY", today: date | None = None) -> dict:
    today = today or date.today()
    if raw is None or (isinstance(raw, float) and pd.isna(raw)) or str(raw).strip() in ("", "NaT"):
        return {"dob_canonical": "", "dob_status": "MISSING"}
    if isinstance(raw, (datetime, pd.Timestamp)):
        d = raw.date()
        return _check_date(d, today)
    if isinstance(raw, date):
        return _check_date(raw, today)
    s = to_ascii_digits(raw).strip().upper()
    s = re.sub(r"\s+00:00:00$", "", s)
    try:
        m = re.fullmatch(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", s)
        if m:
            return _check_date(date(int(m[1]), int(m[2]), int(m[3])), today)
        m = re.fullmatch(r"(\d{1,2})[-/. ]([A-Z]{3,9})[-/. ,]+(\d{4})", s)
        if m and m[2][:3] in _MONTHS:
            return _check_date(date(int(m[3]), _MONTHS[m[2][:3]], int(m[1])), today)
        m = re.fullmatch(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{2}|\d{4})", s)
        if m:
            a, b, y = int(m[1]), int(m[2]), int(m[3])
            if y < 100:
                y += 1900 if y > today.year % 100 else 2000
            if convention.startswith("AUTO"):
                if a <= 12 and b <= 12 and a != b:
                    return {"dob_canonical": "", "dob_status": "AMBIGUOUS"}
                day, mon = (a, b) if a > 12 else (b, a) if b > 12 else (a, b)
            elif convention == "MM/DD/YYYY":
                mon, day = a, b
            else:
                day, mon = a, b
            return _check_date(date(y, mon, day), today)
    except ValueError:
        return {"dob_canonical": "", "dob_status": "INVALID"}
    return {"dob_canonical": "", "dob_status": "INVALID"}


def _check_date(d: date, today: date) -> dict:
    if d > today:
        return {"dob_canonical": d.isoformat(), "dob_status": "FUTURE"}
    if d.year < 1900:
        return {"dob_canonical": d.isoformat(), "dob_status": "OUT_OF_RANGE"}
    return {"dob_canonical": d.isoformat(), "dob_status": "VALID"}


def dob_score(a: str, b: str):
    if not a or not b:
        return None
    if a == b:
        return 1.0
    ya, ma, da = a.split("-")
    yb, mb, db = b.split("-")
    if ya == yb and ma == db and da == mb:  # day/month swapped
        return 0.6
    return 0.0


# =====================================================================
# 6. Address intelligence
# =====================================================================
ADDRESS_DICT = {
    "RD": "ROAD", "ROD": "ROAD", "MARG": "ROAD", "MARGA": "ROAD", "MRG": "ROAD",
    "MG": "MAHATMA GANDHI", "EMJI": "MAHATMA GANDHI", "EMAJI": "MAHATMA GANDHI", "M.G.": "MAHATMA GANDHI",
    "CG": "C G", "SIJI": "C G", "SIJ": "C G",
    "ST": "STREET", "STR": "STREET", "NR": "NEAR", "OPP": "OPPOSITE", "SOC": "SOCIETY", "SOSAYTI": "SOCIETY",
    "SOSAYATI": "SOCIETY", "SOSAITI": "SOCIETY", "SEKTAR": "SECTOR", "SEC": "SECTOR", "STESHAN": "STATION",
    "STN": "STATION", "ASHRM": "ASHRAM", "KALAWAD": "KALAVAD", "RING": "RING", "AHD": "AHMEDABAD",
    "AMDAVAD": "AHMEDABAD", "AMADAVAD": "AHMEDABAD", "AHMADABAD": "AHMEDABAD", "AHAMDABAD": "AHMEDABAD",
    "AHMDABAD": "AHMEDABAD", "AHAMADABAD": "AHMEDABAD", "AMDABAD": "AHMEDABAD",
    "BARODA": "VADODARA", "VADODRA": "VADODARA", "VADODRAA": "VADODARA", "BRD": "VADODARA",
    "SURT": "SURAT", "RAJKT": "RAJKOT", "GNR": "GANDHINAGAR", "GANDHINGR": "GANDHINAGAR",
    "NAVRANGPUR": "NAVRANGPURA", "NAVARANGPURA": "NAVRANGPURA", "NAVRANGAPURA": "NAVRANGPURA", "GANDHINGAR": "GANDHINAGAR", "MANINGAR": "MANINAGAR", "MANINAGR": "MANINAGAR", "MANINGR": "MANINAGAR", "ADAJN": "ADAJAN",
    "ALKAPURI": "ALKAPURI",
}
CITIES = {"AHMEDABAD": "AHMEDABAD", "SURAT": "SURAT", "VADODARA": "VADODARA", "RAJKOT": "RAJKOT",
          "GANDHINAGAR": "GANDHINAGAR", "BHAVNAGAR": "BHAVNAGAR", "JAMNAGAR": "JAMNAGAR", "ANAND": "ANAND"}
_PIN_RE = re.compile(r"\b(\d{6})\b")
_HOUSE_RE = re.compile(r"^(?:NO\s*)?([A-Z]{0,2}[-/]?\d+[A-Z]?(?:[-/]\d+)?)\b")


def gujarat_pin(pin: str) -> bool:
    return bool(pin) and pin.isdigit() and len(pin) == 6 and 360000 <= int(pin) <= 396999


def standardise_address(raw, pin_raw=None, district_raw=None) -> dict:
    out = {"addr_canonical": "", "addr_house": "", "addr_street": "", "addr_city": "", "addr_pin": "", "addr_script": "NONE"}
    if raw is None or (isinstance(raw, float) and pd.isna(raw)) or str(raw).strip() == "":
        if pin_raw is not None and str(pin_raw).strip() not in ("", "nan"):
            out["addr_pin"] = re.sub(r"\D", "", to_ascii_digits(str(pin_raw).split(".")[0]))
        return out
    out["addr_script"] = detect_script(raw)
    t = roman_upper(transliterate(raw), "none" if out["addr_script"] == "LATIN" else "indic")
    t = t.replace("M.G.", "MG ").replace("C.G.", "CG ")
    t = re.sub(r"[^A-Z0-9/\- ]", " ", t)
    tokens = []
    for tok in t.split():
        rep = ADDRESS_DICT.get(tok, tok)
        tokens.extend(rep.split())
    # PIN
    pin = ""
    if pin_raw is not None and str(pin_raw).strip() not in ("", "nan"):
        pin = re.sub(r"\D", "", to_ascii_digits(str(pin_raw).split(".")[0]))
    pins = [x for x in tokens if re.fullmatch(r"\d{6}", x)]
    if not pin and pins:
        pin = pins[0]
    tokens = [x for x in tokens if not re.fullmatch(r"\d{6}", x)]
    # city
    city = ""
    for tok in tokens[::-1]:
        if tok in CITIES:
            city = CITIES[tok]
            break
    if not city and district_raw is not None and str(district_raw).strip() not in ("", "nan"):
        d = roman_upper(transliterate(district_raw)).strip()
        city = CITIES.get(ADDRESS_DICT.get(d, d), ADDRESS_DICT.get(d, d))
    tokens = [x for x in tokens if CITIES.get(x) != city]
    # house
    house = ""
    joined = " ".join(tokens)
    m = _HOUSE_RE.match(joined)
    if m:
        house = m[1]
        joined = joined[m.end():].strip()
    street = re.sub(r"\s+", " ", joined).strip(" -/")
    canon = " ".join(x for x in [house, street] if x)
    canon = ", ".join(x for x in [canon, " ".join(y for y in [city, pin] if y)] if x)
    out.update({"addr_canonical": canon, "addr_house": house, "addr_street": street, "addr_city": city, "addr_pin": pin})
    return out


def address_similarity(a: dict, b: dict):
    parts = []
    if a["addr_pin"] and b["addr_pin"]:
        parts.append((0.3, 1.0 if a["addr_pin"] == b["addr_pin"] else 0.0))
    if a["addr_city"] and b["addr_city"]:
        parts.append((0.2, 1.0 if a["addr_city"] == b["addr_city"] else 0.0))
    if a["addr_house"] and b["addr_house"]:
        parts.append((0.25, 1.0 if a["addr_house"].replace("-", "").replace("/", "") == b["addr_house"].replace("-", "").replace("/", "") else 0.0))
    if a["addr_street"] and b["addr_street"]:
        parts.append((0.25, token_similarity(a["addr_street"], b["addr_street"])))
    if not parts:
        return None
    return round(sum(w * s for w, s in parts) / sum(w for w, _ in parts), 4)


# =====================================================================
# 7. Column mapping
# =====================================================================
TARGET_FIELDS = ["source_id", "name", "relation_name", "dob", "gender", "phone", "address", "pin", "district", "updated_on"]
SYNONYMS = {
    "source_id": ["id", "record_id", "ben_id", "patient_id", "property_id", "land_rec_id", "src_id", "reg_no", "beneficiary_id"],
    "name": ["name", "full_name", "applicant_name", "patient_name", "beneficiary_name", "owner_name", "citizen_name", "applicant_nm"],
    "relation_name": ["father_name", "father_or_spouse_name", "spouse_name", "guardian_name", "relation_name", "father_husband_name"],
    "dob": ["dob", "date_of_birth", "birth_date", "owner_dob", "birthdate"],
    "gender": ["gender", "sex"],
    "phone": ["mobile", "mobile_no", "mob_no", "phone", "phone_1", "contact_no", "contact", "phone_no"],
    "address": ["address", "addr", "addr_line1", "residence_address", "property_address", "full_address"],
    "pin": ["pin", "pincode", "pin_code", "postal_code", "zip"],
    "district": ["district", "city", "ward", "taluka"],
    "updated_on": ["updated_on", "last_updated", "modified_date", "updated_at", "last_modified"],
}


def auto_map(columns) -> dict:
    cols = {c.lower().strip(): c for c in columns}
    mapping = {}
    for tgt, syns in SYNONYMS.items():
        mapping[tgt] = None
        for s in syns:
            if s in cols:
                mapping[tgt] = cols[s]
                break
        if mapping[tgt] is None:
            for lc, orig in cols.items():
                if any(s in lc for s in syns[:3]) and orig not in mapping.values():
                    mapping[tgt] = orig
                    break
    return mapping


# =====================================================================
# 8. Standardise + data quality
# =====================================================================
RULES = [
    # code, severity, description
    ("NAME_MISSING", "CRITICAL", "Name is mandatory"),
    ("DOB_INVALID", "CRITICAL", "DOB cannot be parsed or is not a real date"),
    ("DOB_FUTURE", "CRITICAL", "DOB is in the future"),
    ("DOB_AMBIGUOUS", "CRITICAL", "DOB could be DD/MM or MM/DD"),
    ("DOB_OUT_OF_RANGE", "CRITICAL", "DOB before 1900"),
    ("DOB_MISSING", "WARNING", "DOB not provided"),
    ("PHONE_INVALID", "WARNING", "Mobile is not a valid 10-digit Indian number"),
    ("PHONE_MISSING", "WARNING", "Mobile not provided"),
    ("PIN_NOT_IN_STATE", "WARNING", "PIN code outside Gujarat (360000-396999)"),
    ("ADDRESS_MISSING", "WARNING", "Address not provided"),
]
RULE_SEVERITY = {r[0]: r[1] for r in RULES}


def _val(row, col):
    if not col:
        return None
    v = row.get(col)
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    return v


def standardise_source(df: pd.DataFrame, source: str, mapping: dict, convention: str, today=None) -> pd.DataFrame:
    recs = []
    for idx, row in df.iterrows():
        sid = _val(row, mapping.get("source_id"))
        sid = str(sid).split(".0")[0] if sid is not None else f"row{idx + 1}"
        raw = {f: _val(row, mapping.get(f)) for f in TARGET_FIELDS}
        n = standardise_name(raw["name"])
        rel = standardise_name(raw["relation_name"])
        d = standardise_dob(raw["dob"], convention, today)
        p = standardise_phone(raw["phone"])
        a = standardise_address(raw["address"], raw["pin"], raw["district"])
        g = str(raw["gender"] or "").strip().upper()
        gender = "M" if g[:1] in ("M",) or g in ("पुरुष", "પુરુષ") else "F" if g[:1] in ("F",) or g in ("स्त्री", "સ્ત્રી", "महिला", "મહિલા") else ""
        upd = raw["updated_on"]
        try:
            u = to_ascii_digits(upd).strip() if upd is not None else ""
            upd = pd.to_datetime(u, dayfirst=not re.match(r"\d{4}-", u)).date().isoformat() if u else ""
        except Exception:
            upd = ""
        issues = []
        if not n["name_canonical"]:
            issues.append("NAME_MISSING")
        if d["dob_status"] != "VALID":
            issues.append({"MISSING": "DOB_MISSING", "INVALID": "DOB_INVALID", "FUTURE": "DOB_FUTURE", "AMBIGUOUS": "DOB_AMBIGUOUS", "OUT_OF_RANGE": "DOB_OUT_OF_RANGE"}[d["dob_status"]])
        if p["phone_status"] == "INVALID":
            issues.append("PHONE_INVALID")
        elif p["phone_status"] == "MISSING":
            issues.append("PHONE_MISSING")
        if a["addr_pin"] and not gujarat_pin(a["addr_pin"]):
            issues.append("PIN_NOT_IN_STATE")
        if not a["addr_canonical"]:
            issues.append("ADDRESS_MISSING")
        critical = [i for i in issues if RULE_SEVERITY[i] == "CRITICAL"]
        recs.append({
            "uid": f"{source}:{sid}", "source": source, "source_id": sid,
            "name_original": "" if raw["name"] is None else str(raw["name"]),
            **n,
            "relation_original": "" if raw["relation_name"] is None else str(raw["relation_name"]),
            "relation_canonical": rel["name_canonical"],
            "dob_original": "" if raw["dob"] is None else str(raw["dob"]), **d,
            "gender": gender,
            "phone_original": "" if raw["phone"] is None else str(raw["phone"]), **p,
            "address_original": "" if raw["address"] is None else str(raw["address"]), **a,
            "updated_on": upd,
            "issues": issues,
            "quarantine_reason": "; ".join(critical),
            "status": "QUARANTINE" if critical else "PASS",
            "quality_score": round(100 * (1 - len(issues) / 5), 1),
        })
    return pd.DataFrame(recs)


def rule_summary(std: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for code, sev, desc in RULES:
        for src, g in std.groupby("source"):
            fails = int(g["issues"].apply(lambda x: code in x).sum())
            rows.append({"rule": code, "severity": sev, "description": desc, "source": src, "failed": fails,
                         "total": len(g), "pass_rate_%": round(100 * (1 - fails / max(len(g), 1)), 1)})
    return pd.DataFrame(rows)


def source_scores(std: pd.DataFrame) -> pd.DataFrame:
    g = std.groupby("source").agg(records=("uid", "count"), avg_quality=("quality_score", "mean"),
                                  quarantined=("status", lambda s: int((s == "QUARANTINE").sum())))
    g["avg_quality"] = g["avg_quality"].round(1)
    g["passed"] = g["records"] - g["quarantined"]
    return g.reset_index()


# =====================================================================
# 9. Matching
# =====================================================================
DEFAULT_WEIGHTS = {"name": 0.30, "dob": 0.25, "phone": 0.20, "address": 0.25}


def _blocks(df: pd.DataFrame):
    keys = defaultdict(list)
    for r in df.itertuples():
        toks = r.name_phonetic.split()
        surname = toks[-1] if toks else ""
        first = toks[0] if toks else ""
        year = r.dob_canonical[:4] if r.dob_canonical else ""
        if r.phone_canonical:
            keys[("PH", r.phone_canonical)].append(r.Index)
        if surname and year:
            keys[("SY", surname, year)].append(r.Index)
        if first and year:
            keys[("FY", first, year)].append(r.Index)
        if r.dob_canonical and r.name_canonical:
            keys[("DN", r.dob_canonical, r.name_canonical[:1])].append(r.Index)
        if r.addr_pin and first:
            keys[("PF", r.addr_pin, first)].append(r.Index)
    pairs = set()
    for k, idxs in keys.items():
        if len(idxs) > 300:
            continue
        for i in range(len(idxs)):
            for j in range(i + 1, len(idxs)):
                a, b = sorted((idxs[i], idxs[j]))
                pairs.add((a, b))
    return pairs


def score_pairs(df: pd.DataFrame, weights=None, auto_t=0.92, review_t=0.75) -> pd.DataFrame:
    weights = weights or DEFAULT_WEIGHTS
    df = df.reset_index(drop=True)
    rows = []
    recs = df.to_dict("records")
    for i, j in _blocks(df):
        a, b = recs[i], recs[j]
        feats = {
            "name": name_similarity(a, b),
            "dob": dob_score(a["dob_canonical"], b["dob_canonical"]),
            "phone": (1.0 if a["phone_canonical"] == b["phone_canonical"] else 0.0) if a["phone_canonical"] and b["phone_canonical"] else None,
            "address": address_similarity(a, b),
        }
        avail = {k: v for k, v in feats.items() if v is not None}
        wsum = sum(weights[k] for k in avail)
        if wsum == 0:
            continue
        score = sum(weights[k] * v for k, v in avail.items()) / wsum
        coverage = wsum / sum(weights.values())
        flags = []
        if feats["dob"] == 0.0:
            flags.append("DOB_CONFLICT")
        if feats["dob"] == 0.6:
            flags.append("DOB_DAY_MONTH_SWAP")
        if feats["phone"] == 1.0 and (feats["name"] or 0) < 0.85:
            flags.append("SHARED_PHONE_DIFFERENT_NAME")
        if coverage < 0.6:
            flags.append("LOW_EVIDENCE")
        if a["gender"] and b["gender"] and a["gender"] != b["gender"]:
            flags.append("GENDER_CONFLICT")
        if (feats["name"] or 0) < 0.80:
            decision = "NO_MATCH"
        elif score >= auto_t and not flags:
            decision = "AUTO_MERGE"
        elif score >= review_t and "GENDER_CONFLICT" not in flags and "SHARED_PHONE_DIFFERENT_NAME" not in flags:
            decision = "REVIEW"
        elif "DOB_CONFLICT" in flags and (feats["name"] or 0) >= 0.95 and score >= 0.6:
            decision = "REVIEW"
        elif (feats["name"] or 0) >= 0.95 and feats["dob"] == 1.0 and "GENDER_CONFLICT" not in flags:
            flags.append("CONTACT_CHANGED")
            decision = "REVIEW"
        else:
            decision = "NO_MATCH"
        rows.append({
            "pair_id": f"{a['uid']}|{b['uid']}", "uid_a": a["uid"], "uid_b": b["uid"],
            "name_a": a["name_display"], "name_b": b["name_display"],
            "name_orig_a": a["name_original"], "name_orig_b": b["name_original"],
            "dob_a": a["dob_canonical"], "dob_b": b["dob_canonical"],
            "phone_a": a["phone_canonical"], "phone_b": b["phone_canonical"],
            "addr_a": a["addr_canonical"], "addr_b": b["addr_canonical"],
            "s_name": feats["name"], "s_dob": feats["dob"], "s_phone": feats["phone"], "s_address": feats["address"],
            "score": round(score, 4), "coverage": round(coverage, 2), "flags": ", ".join(flags), "decision": decision,
        })
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values("score", ascending=False).reset_index(drop=True)
    return out


# =====================================================================
# 10. Clustering, survivorship, golden record
# =====================================================================
class _UF:
    def __init__(self, items):
        self.p = {x: x for x in items}

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)


def build_golden(df: pd.DataFrame, pairs: pd.DataFrame, decisions: dict, trust: dict):
    """decisions: pair_id -> 'APPROVE' | 'REJECT'. trust: source -> rank (1 = most trusted)."""
    uf = _UF(df["uid"].tolist())
    merged_pairs = []
    if not pairs.empty:
        for r in pairs.itertuples():
            d = decisions.get(r.pair_id)
            if d == "REJECT":
                continue
            if r.decision == "AUTO_MERGE" or d == "APPROVE":
                uf.union(r.uid_a, r.uid_b)
                merged_pairs.append(r)
    clusters = defaultdict(list)
    for uid in df["uid"]:
        clusters[uf.find(uid)].append(uid)
    by_uid = df.set_index("uid").to_dict("index")
    pair_score = {}
    for r in merged_pairs:
        root = uf.find(r.uid_a)
        pair_score[root] = min(pair_score.get(root, 1.0), r.score)

    def rank(u):
        rec = by_uid[u]
        return (trust.get(rec["source"], 99), -(int(rec["updated_on"].replace("-", "")) if rec["updated_on"] else 0))

    golden, xwalk = [], []
    for n, (root, members) in enumerate(sorted(clusters.items(), key=lambda kv: sorted(kv[1])[0]), start=1):
        mid = f"GJ{n:07d}"
        recs = sorted(members, key=rank)
        R = [by_uid[u] | {"uid": u} for u in recs]
        prov = {}

        def pick(field, pred=lambda r: True, prefer_latin=False, key=None):
            cands = [r for r in R if r.get(field) and pred(r)]
            if prefer_latin:
                lat = [r for r in cands if r.get("name_script" if field.startswith("name") else "addr_script") == "LATIN"]
                cands = lat or cands
            if key:
                cands = sorted(cands, key=key)
            if not cands:
                return "", ""
            return cands[0][field], cands[0]["uid"]

        votes = Counter(r["name_display"] for r in R if r["name_display"])
        if votes:
            top = max(votes.values())
            winner = next(r for r in sorted(R, key=lambda r: 0 if r["name_script"] == "LATIN" else 1) if votes.get(r["name_display"]) == top)
            name, prov["name"] = winner["name_display"], winner["uid"]
        else:
            name, prov["name"] = "", ""
        # DOB: most frequent valid value, tie -> most trusted
        dobs = [r["dob_canonical"] for r in R if r["dob_status"] == "VALID"]
        if dobs:
            cnt = Counter(dobs)
            best = max(cnt.values())
            dob = next(r["dob_canonical"] for r in R if r["dob_status"] == "VALID" and cnt[r["dob_canonical"]] == best)
            prov["dob"] = next(r["uid"] for r in R if r["dob_canonical"] == dob)
        else:
            dob, prov["dob"] = "", ""
        latest = lambda r: -(int(r["updated_on"].replace("-", "")) if r["updated_on"] else 0)
        phone, prov["phone"] = pick("phone_canonical", key=latest)
        addr_rec = sorted([r for r in R if r["addr_canonical"]], key=lambda r: (0 if r["addr_script"] == "LATIN" else 1, latest(r)))
        addr = addr_rec[0] if addr_rec else {}
        prov["address"] = addr.get("uid", "")
        gender, prov["gender"] = pick("gender")
        rel, prov["relation"] = pick("relation_canonical")
        local = next((r["name_original"] for r in R if r["name_script"] == "GUJARATI"), "")
        golden.append({
            "master_id": mid, "name": name, "name_gujarati": local, "dob": dob, "gender": gender, "phone": phone,
            "address": addr.get("addr_canonical", ""), "house": addr.get("addr_house", ""),
            "street": addr.get("addr_street", ""), "city": addr.get("addr_city", ""), "pin": addr.get("addr_pin", ""),
            "father_or_spouse": rel, "source_count": len(R),
            "sources": ", ".join(sorted({r["source"] for r in R})),
            "match_confidence": round(pair_score.get(root, 1.0), 4),
            "provenance": "; ".join(f"{k}<-{v.split(':')[0]}" for k, v in prov.items() if v),
        })
        for r in R:
            xwalk.append({"master_id": mid, "uid": r["uid"], "source": r["source"], "source_id": r["source_id"],
                          "name_original": r["name_original"], "dob_original": r["dob_original"],
                          "phone_original": r["phone_original"], "address_original": r["address_original"]})
    g = pd.DataFrame(golden)
    g = assign_households(g)
    return g, pd.DataFrame(xwalk)


def assign_households(g: pd.DataFrame) -> pd.DataFrame:
    if g.empty:
        g["household_id"] = []
        return g
    recs = g.to_dict("records")
    uf = _UF(list(range(len(recs))))
    surname = lambda r: phonetic(r["name"].split()[-1]) if r["name"] else ""
    by_addr = defaultdict(list)
    for i, r in enumerate(recs):
        if r["house"] and r["pin"]:
            by_addr[(r["house"].replace("-", ""), r["pin"])].append(i)
    for idxs in by_addr.values():
        for x in idxs:
            for y in idxs:
                if x < y and (surname(recs[x]) == surname(recs[y]) or _is_relation(recs[x], recs[y])):
                    uf.union(x, y)
    by_phone = defaultdict(list)
    for i, r in enumerate(recs):
        if r["phone"]:
            by_phone[r["phone"]].append(i)
    for idxs in by_phone.values():
        for x in idxs:
            for y in idxs:
                if x < y and surname(recs[x]) == surname(recs[y]):
                    uf.union(x, y)
    groups = defaultdict(list)
    for i in range(len(recs)):
        groups[uf.find(i)].append(i)
    hh = {}
    n = 0
    for root, members in sorted(groups.items()):
        n += 1
        for m in members:
            hh[m] = f"H-{n:04d}"
    g = g.copy()
    g["household_id"] = [hh[i] for i in range(len(recs))]
    g["household_size"] = g.groupby("household_id")["master_id"].transform("count")
    return g


def _is_relation(a, b):
    def first(s):
        return s.split()[0] if s else ""
    return (a["father_or_spouse"] and first(a["father_or_spouse"]) == first(b["name"])) or \
           (b["father_or_spouse"] and first(b["father_or_spouse"]) == first(a["name"]))


# =====================================================================
# 11. Search
# =====================================================================
def search_golden(g: pd.DataFrame, query: str, min_score=0.8, limit=20) -> pd.DataFrame:
    if g.empty or not query.strip():
        return g.head(0)
    q = query.strip()
    qd = re.sub(r"\D", "", to_ascii_digits(q))
    if len(qd) >= 7 and len(qd) >= len(q.replace(" ", "")) * 0.6:
        p = standardise_phone(q)["phone_canonical"] or qd
        res = g[g["phone"].str.contains(p[-10:], na=False)].copy()
        res["search_score"] = 1.0
        return res
    qn = standardise_name(q)
    scores = []
    for r in g.itertuples():
        rn = {"name_canonical": r.name, "name_phonetic": " ".join(phonetic(x) for x in r.name.split())}
        s = name_similarity(qn, rn) or 0
        if len(qn["name_canonical"].split()) == 1:  # single token query: best token
            s = max(s, max((jaro_winkler(qn["name_canonical"], t) for t in r.name.split()), default=0),
                    0.97 if qn["name_phonetic"] in rn["name_phonetic"].split() else 0)
        scores.append(s)
    res = g.copy()
    res["search_score"] = [round(x, 3) for x in scores]
    res = res[res["search_score"] >= min_score].sort_values("search_score", ascending=False).head(limit)
    return res


# =====================================================================
# 12. One-call pipeline
# =====================================================================
def run_pipeline(sources: list, decisions: dict | None = None, weights=None, auto_t=0.92, review_t=0.75, today=None):
    """sources: list of dicts {name, df, mapping, convention, trust}."""
    decisions = decisions or {}
    std = pd.concat([standardise_source(s["df"], s["name"], s["mapping"], s["convention"], today) for s in sources], ignore_index=True)
    passed = std[std["status"] == "PASS"].reset_index(drop=True)
    pairs = score_pairs(passed, weights, auto_t, review_t)
    trust = {s["name"]: s["trust"] for s in sources}
    golden, xwalk = build_golden(passed, pairs, decisions, trust)
    return {
        "standardised": std,
        "quarantine": std[std["status"] == "QUARANTINE"].reset_index(drop=True),
        "rules": rule_summary(std),
        "source_scores": source_scores(std),
        "pairs": pairs,
        "golden": golden,
        "crosswalk": xwalk,
    }
