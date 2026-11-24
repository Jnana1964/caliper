"""Fictional test corpus.

These are INVENTED schemes with INVENTED rules. They exist only so the test
suite can run deterministically offline. Nothing here describes a real Indian
government scheme and nothing here should ever be quoted as if it did.
"""

from app.store import chunk_text

FIXTURE_DOCS = [
    (
        "fictional-scheme-a.txt",
        """
        Fictional Farmer Support Scheme (FFSS) - Operational Guidelines

        Eligibility. A cultivator household owning not more than 2 hectares of
        cultivable land is eligible under FFSS. Households where any member paid
        income tax in the preceding assessment year are excluded.

        Benefit. Eligible households receive 9,000 rupees per year, paid in three
        equal instalments of 3,000 rupees directly to the registered bank account.

        Documents required. Aadhaar, land record extract, and a bank passbook
        showing the account number and IFSC code.
        """,
    ),
    (
        "fictional-scheme-b.txt",
        """
        Fictional Student Merit Grant (FSMG) - Scheme Document

        Eligibility. Students who scored 80 percent or above in Class XII and
        whose annual family income does not exceed 4,50,000 rupees may apply.

        Benefit. A grant of 25,000 rupees per academic year for a maximum of four
        years, subject to maintaining 75 percent attendance.

        Application window. Applications open on 1 July and close on 30 September
        each year. Late applications are not considered.
        """,
    ),
]


def fixture_chunks():
    out = []
    for name, body in FIXTURE_DOCS:
        out += chunk_text(body, source=name, doc_id=name.replace(".txt", ""), page=1)
    return out
