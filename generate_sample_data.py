"""
Generate synthetic multilingual citizen files for 4 Gujarat departments.
All people, numbers and addresses are fictitious.

    python generate_sample_data.py      -> writes ./sample_data/*
"""
import random
from pathlib import Path

import pandas as pd

random.seed(26)
OUT = Path(__file__).parent / "sample_data"
OUT.mkdir(exist_ok=True)

GU_DIGITS = str.maketrans("0123456789", "૦૧૨૩૪૫૬૭૮૯")
HI_DIGITS = str.maketrans("0123456789", "०१२३४५६७८९")

FIRST = {  # english: (gujarati, hindi, gender)
    "Rahul": ("રાહુલ", "राहुल", "M"), "Rakesh": ("રાકેશ", "राकेश", "M"), "Meena": ("મીના", "मीना", "F"),
    "Kiran": ("કિરણ", "किरण", "F"), "Amit": ("અમિત", "अमित", "M"), "Priya": ("પ્રિયા", "प्रिया", "F"),
    "Suresh": ("સુરેશ", "सुरेश", "M"), "Neha": ("નેહા", "नेहा", "F"), "Vijay": ("વિજય", "विजय", "M"),
    "Pooja": ("પૂજા", "पूजा", "F"), "Mahesh": ("મહેશ", "महेश", "M"), "Anita": ("અનિતા", "अनिता", "F"),
    "Jignesh": ("જીગ્નેશ", "जिग्नेश", "M"), "Hetal": ("હેતલ", "हेतल", "F"), "Bhavesh": ("ભાવેશ", "भावेश", "M"),
    "Komal": ("કોમલ", "कोमल", "F"), "Nilesh": ("નિલેશ", "निलेश", "M"), "Kavita": ("કવિતા", "कविता", "F"),
    "Dinesh": ("દિનેશ", "दिनेश", "M"), "Sonal": ("સોનલ", "सोनल", "F"), "Arjun": ("અર્જુન", "अर्जुन", "M"),
    "Ramesh": ("રમેશ", "रमेश", "M"), "Geeta": ("ગીતા", "गीता", "F"), "Harsh": ("હર્ષ", "हर्ष", "M"),
}
LAST = {"Sharma": ("શર્મા", "शर्मा"), "Shah": ("શાહ", "शाह"), "Patel": ("પટેલ", "पटेल"), "Desai": ("દેસાઈ", "देसाई"),
        "Mehta": ("મહેતા", "मेहता"), "Joshi": ("જોશી", "जोशी"), "Parmar": ("પરમાર", "परमार"),
        "Chauhan": ("ચૌહાણ", "चौहान"), "Trivedi": ("ત્રિવેદી", "त्रिवेदी"), "Solanki": ("સોલંકી", "सोलंकी")}
# street: (english, english-short, gujarati, hindi), locality, city, pin
PLACES = [
    (("Mahatma Gandhi Road", "MG Rd", "એમજી રોડ", "महात्मा गांधी मार्ग"), ("Navrangpura", "નવરંગપુરા", "नवरंगपुरा"), ("Ahmedabad", "અમદાવાદ", "अहमदाबाद"), "380009"),
    (("C G Road", "CG Road", "સીજી રોડ", "सीजी रोड"), ("Navrangpura", "નવરંગપુરા", "नवरंगपुरा"), ("Ahmedabad", "અમદાવાદ", "अहमदाबाद"), "380009"),
    (("Ashram Road", "Ashram Rd", "આશ્રમ રોડ", "आश्रम रोड"), ("Maninagar", "મણિનગર", "मणिनगर"), ("Ahmedabad", "અમદાવાદ", "अहमदाबाद"), "380008"),
    (("Station Road", "Stn Rd", "સ્ટેશન રોડ", "स्टेशन रोड"), ("Alkapuri", "અલકાપુરી", "अलकापुरी"), ("Vadodara", "વડોદરા", "वडोदरा"), "390007"),
    (("Ring Road", "Ring Rd", "રિંગ રોડ", "रिंग रोड"), ("Adajan", "અડાજણ", "अडाजण"), ("Surat", "સુરત", "सूरत"), "395009"),
    (("Kalawad Road", "Kalawad Rd", "કાલાવડ રોડ", "कालावड रोड"), ("", "", ""), ("Rajkot", "રાજકોટ", "राजकोट"), "360005"),
    (("Sector 21", "Sec 21", "સેક્ટર ૨૧", "सेक्टर २१"), ("", "", ""), ("Gandhinagar", "ગાંધીનગર", "गांधीनगर"), "382021"),
]


def mobile():
    return random.choice("6789") + "".join(random.choice("0123456789") for _ in range(9))


# ---------------------------------------------------------------- people
people = []
firsts_m = [k for k, v in FIRST.items() if v[2] == "M"]
firsts_f = [k for k, v in FIRST.items() if v[2] == "F"]
pid = 0
for h in range(16):  # 16 households
    last = list(LAST)[h % len(LAST)]
    place = PLACES[h % len(PLACES)]
    house = str(random.choice([12, 7, 45, 101, 23, 9, 56, 88, 14, 3, 210, 31, 64, 5, 19, 77])[0] if False else [12, 7, 45, 101, 23, 9, 56, 88, 14, 3, 210, 31, 64, 5, 19, 77][h])
    phone_home = mobile()
    head = "Rahul" if h == 0 else random.choice(firsts_m)
    spouse = random.choice(firsts_f)
    y = 1985 if h == 0 else random.randint(1962, 1990)
    members = [(head, "M", f"{y}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}", "Head", None),
               (spouse, "F", f"{y + random.randint(1, 4)}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}", "Spouse", head)]
    if h % 3 != 2:
        child = random.choice(firsts_m + firsts_f)
        members.append((child, FIRST[child][2], f"{y + random.randint(22, 30)}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}", "Child", head))
    if h == 1:  # father & son with the same name (must NOT merge)
        members.append((head, "M", f"{y + 26}-03-15", "Child", head))
    for first, g, dob, role, rel in members:
        pid += 1
        people.append({"pid": pid, "first": first, "last": last, "gender": g, "dob": dob, "role": role,
                       "relation": rel, "hh": h, "place": place, "house": house,
                       "phone": phone_home if role != "Child" or random.random() < 0.3 else mobile()})
people[0].update(dob="1985-05-10", phone="9876543210")  # the Rahul Sharma of the deck

# --------------------------------------------------------------- formatters
def name_en(p, typo=False):
    f = p["first"]
    if typo:
        f = {"Rahul": "Raahul", "Jignesh": "Jignes", "Pooja": "Puja", "Geeta": "Gita", "Bhavesh": "Bhavesh"}.get(f, f + "")
    return f"{f} {p['last']}"


def name_gu(p):
    return f"{FIRST[p['first']][0]} {LAST[p['last']][0]}"


def name_hi(p):
    return f"{FIRST[p['first']][1]} {LAST[p['last']][1]}"


def rel_en(p):
    return f"{p['relation']} {p['last']}" if p["relation"] else ""


def addr_en(p, short=False):
    st, loc, city, pin = p["place"]
    parts = [f"{p['house']} {st[1] if short else st[0]}"] + ([loc[0]] if loc[0] else []) + [city[0]]
    return ", ".join(parts)


def addr_gu(p):
    st, loc, city, pin = p["place"]
    return ", ".join([f"{p['house'].translate(GU_DIGITS)} {st[2]}"] + ([loc[1]] if loc[1] else []) + [city[1]])


def addr_hi(p):
    st, loc, city, pin = p["place"]
    return ", ".join([f"{p['house'].translate(HI_DIGITS)} {st[3]}"] + ([loc[2]] if loc[2] else []) + [city[2]])


def d(iso, fmt):
    y, m, dd = iso.split("-")
    mon = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][int(m) - 1]
    return {"dmy-": f"{dd}-{m}-{y}", "dmy/": f"{dd}/{m}/{y}", "iso": iso, "text": f"{int(dd)} {mon} {y}"}[fmt]


def upd():
    return f"2026-{random.randint(1, 10):02d}-{random.randint(1, 28):02d}"


# --------------------------------------------------------------- Revenue (English, DD-MM-YYYY)
rows = []
for p in people:
    if random.random() < 0.85 and p["role"] != "Child" or random.random() < 0.4:
        rows.append({"land_rec_id": f"REV{1000 + p['pid']}", "applicant_name": name_en(p), "father_name": rel_en(p),
                     "dob": d(p["dob"], "dmy-"), "gender": "Male" if p["gender"] == "M" else "Female",
                     "mobile_no": p["phone"], "address": addr_en(p, short=True) + " " + p["place"][3],
                     "district": p["place"][2][0], "last_updated": upd()})
rev = pd.DataFrame(rows)
# within-source duplicate (same person registered twice, typo)
dup = rev.iloc[3].copy(); dup["land_rec_id"] = "REV9001"; dup["applicant_name"] = dup["applicant_name"].upper().replace("A", "AA", 1)
rev = pd.concat([rev, dup.to_frame().T], ignore_index=True)
rev.to_csv(OUT / "revenue_land_records.csv", index=False, encoding="utf-8-sig")

# --------------------------------------------------------------- Health (Gujarati, DD/MM/YYYY Gujarati digits)
rows = []
for p in people:
    if random.random() < 0.75:
        guj = random.random() < 0.7
        ph = p["phone"]
        rows.append({"patient_id": f"HLT-{5000 + p['pid']}", "patient_name": name_gu(p) if guj else name_en(p),
                     "dob": d(p["dob"], "dmy/").translate(GU_DIGITS) if guj else d(p["dob"], "dmy/"),
                     "sex": "પુરુષ" if (guj and p["gender"] == "M") else "સ્ત્રી" if guj else p["gender"],
                     "contact_no": f"{ph[:5]} {ph[5:]}".translate(GU_DIGITS) if guj else ph,
                     "residence_address": addr_gu(p) if guj else addr_en(p),
                     "pin": p["place"][3].translate(GU_DIGITS) if guj else p["place"][3], "updated_on": upd()})
hlt = pd.DataFrame(rows)
hlt.loc[2, "dob"] = "૧૨/૧૨/૨૦૩૧"  # future DOB -> quarantine
hlt.to_csv(OUT / "health_patients.csv", index=False, encoding="utf-8-sig")

# --------------------------------------------------------------- Welfare (Hindi / English typos, ISO dates, +91)
rows = []
for p in people:
    if random.random() < 0.7:
        hindi = random.random() < 0.4
        rows.append({"ben_id": f"SJE{20000 + p['pid']}", "beneficiary_name": name_hi(p) if hindi else name_en(p, typo=True),
                     "father_or_spouse_name": rel_en(p), "date_of_birth": p["dob"],
                     "gender": "F" if p["gender"] == "F" else "M",
                     "mobile": f"+91 {p['phone'][:5]} {p['phone'][5:]}",
                     "addr_line1": addr_hi(p) if hindi else addr_en(p), "pin_code": p["place"][3],
                     "scheme": random.choice(["PMAY-G", "NFSA", "MA-Yojana", "Vahli Dikri"]), "updated_on": upd()})
wel = pd.DataFrame(rows)
wel.loc[4, "beneficiary_name"] = ""  # missing name -> quarantine
wel.to_excel(OUT / "social_welfare_beneficiaries.xlsx", index=False)

# --------------------------------------------------------------- Municipal (UPPER, text dates, messy phones)
rows = []
for p in people:
    if p["role"] == "Head" or random.random() < 0.35:
        ph = p["phone"]
        rows.append({"property_id": f"AMC/{p['pid']:04d}", "owner_name": name_en(p).upper(),
                     "owner_dob": d(p["dob"], "text"), "phone_1": random.choice([f"0091-{ph}", f"0{ph}", ph]),
                     "property_address": addr_en(p, short=True).upper(), "pin": p["place"][3],
                     "ward": p["place"][2][0].upper(), "updated_on": upd()})
mun = pd.DataFrame(rows)
mun.loc[1, "phone_1"] = "98765432"      # invalid phone -> warning
mun.loc[3, "pin"] = "110001"            # Delhi PIN -> warning
mun.loc[5, "owner_dob"] = "31 Feb 1979"  # impossible date -> quarantine

# ---- doubtful cases for the steward review queue ------------------------------
def _row(df, col, prefix_pid):
    return df.index[df[col] == prefix_pid][0] if (df[col] == prefix_pid).any() else None
# 1) Welfare: day and month swapped (10 May vs 5 Oct)
i = _row(wel, "ben_id", "SJE20001")
if i is not None:
    wel.loc[i, "date_of_birth"] = "1985-10-05"
# 2) Municipal: owner moved house and changed number, name abbreviated
for pid_ in (10, 22):
    i = _row(mun, "property_id", f"AMC/{pid_:04d}")
    if i is not None:
        mun.loc[i, "phone_1"] = mobile()
        mun.loc[i, "property_address"] = "B-14 SHANTI SOC, VASTRAPUR, AHMEDABAD"
        mun.loc[i, "pin"] = "380015"
# 3) Health: walk-in patient with only name + DOB (no phone, no address)
i = _row(hlt, "patient_id", "HLT-5007")
if i is not None:
    hlt.loc[i, ["contact_no", "residence_address", "pin"]] = ["", "", ""]
hlt.to_csv(OUT / "health_patients.csv", index=False, encoding="utf-8-sig")
wel.to_excel(OUT / "social_welfare_beneficiaries.xlsx", index=False)
mun.to_csv(OUT / "municipal_property_tax.csv", index=False, encoding="utf-8-sig")

truth = pd.DataFrame([{"person_id": p["pid"], "name": name_en(p), "dob": p["dob"], "household": f"HH{p['hh'] + 1:02d}", "role": p["role"]} for p in people])
truth.to_csv(OUT / "_ground_truth_people.csv", index=False)
print({f.name: len(pd.read_csv(f) if f.suffix == ".csv" else pd.read_excel(f)) for f in OUT.iterdir()})
