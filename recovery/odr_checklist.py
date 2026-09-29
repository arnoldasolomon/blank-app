"""What a micro/small supplier needs before filing on odr.msme.gov.in."""

ELIGIBILITY = [
    "Supplier is a micro or small enterprise (medium enterprises cannot file under Section 18).",
    "Valid Udyam registration that existed before the supply was made.",
    "Buyer has not paid within the agreed period (max 45 days) or 15 days if there was no written agreement.",
    "Claim is within 3 years of the amount falling due (older claims may be time-barred).",
]

DOCUMENTS = [
    "Udyam registration certificate",
    "Purchase order / work order / written contract with the buyer",
    "Tax invoices for each unpaid supply",
    "Proof of delivery: delivery challan, e-way bill, LR/transport receipt or signed GRN",
    "Buyer's ledger / account statement showing outstanding balance",
    "Proof of any part payments received (bank statement extracts)",
    "Copies of reminders and replies (email, WhatsApp screenshots, letters)",
    "Buyer details: legal name, registered address, GSTIN, PAN, contact person",
    "Interest calculation sheet (export from this tool)",
]

STEPS = [
    "Register on odr.msme.gov.in using your Udyam number and verify with OTP.",
    "Create a new case: add buyer details and each invoice with dates and amounts.",
    "Upload the documents above as PDFs.",
    "Submit. The case starts in the voluntary pre-MSEFC online negotiation stage "
    "(closes within 15 days, or 30 if both sides agree).",
    "If unresolved, it escalates to the Facilitation Council for conciliation, then arbitration; "
    "Section 18(5) expects a decision within 90 days of reference.",
    "Track hearings and notices on the portal; attend online sessions when scheduled.",
]
