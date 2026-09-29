from datetime import date
from urllib.parse import quote

import pandas as pd
import streamlit as st

from recovery import odr_checklist
from recovery.interest import Invoice, evaluate_invoice, format_inr, statutory_annual_rate
from recovery.templates import LANGUAGES, TIERS, render

st.set_page_config(page_title="MSME Payment Recovery", page_icon="₹", layout="wide")

st.title("₹ MSME Payment Recovery")
st.caption(
    "Work out what a buyer legally owes under the MSMED Act, 2006, draft escalating reminders, "
    "and prepare for filing on the MSME ODR portal."
)

with st.sidebar:
    st.header("Supplier")
    supplier = st.text_input("Business name", "Your Business Pvt Ltd")
    udyam = st.text_input("Udyam registration no.", "UDYAM-MH-00-0000000")
    udyam_date = st.date_input("Udyam registration date", date(2022, 4, 1))
    category = st.radio("Enterprise category", ["Micro", "Small", "Medium"], horizontal=True)

    st.header("Buyer")
    buyer = st.text_input("Buyer name", "Buyer Industries Ltd")

    st.header("Calculation")
    as_of = st.date_input("Calculate as of", date.today())
    bank_rate = st.number_input(
        "RBI bank rate (%)",
        min_value=0.0,
        max_value=20.0,
        value=5.50,
        step=0.05,
        help="5.50% as of RBI's 5 Aug 2026 policy. Check rbi.org.in after each policy review.",
    )
    st.caption(f"Statutory rate: {statutory_annual_rate(bank_rate):.2%} p.a., compounded monthly")

if category == "Medium":
    st.error(
        "Sections 16 and 18 of the MSMED Act protect micro and small suppliers only. "
        "A medium enterprise cannot claim statutory interest or file on the ODR portal."
    )
    st.stop()

SAMPLE = pd.DataFrame(
    [
        {"invoice_no": "INV-101", "delivery_date": date(2026, 3, 10), "amount": 250000.0,
         "amount_paid": 0.0, "written_agreement": True, "agreed_credit_days": 45},
        {"invoice_no": "INV-117", "delivery_date": date(2026, 5, 2), "amount": 180000.0,
         "amount_paid": 50000.0, "written_agreement": False, "agreed_credit_days": 0},
    ]
)

tab_calc, tab_remind, tab_odr = st.tabs(["1. Invoices & interest", "2. Reminders", "3. ODR filing checklist"])

with tab_calc:
    uploaded = st.file_uploader(
        "Upload a CSV (optional)",
        type="csv",
        help="Columns: invoice_no, delivery_date (YYYY-MM-DD), amount, amount_paid, "
        "written_agreement (true/false), agreed_credit_days",
    )
    source = SAMPLE
    if uploaded is not None:
        source = pd.read_csv(uploaded, parse_dates=["delivery_date"])
        source["delivery_date"] = source["delivery_date"].dt.date

    invoices_df = st.data_editor(
        source,
        num_rows="dynamic",
        width="stretch",
        column_config={
            "invoice_no": st.column_config.TextColumn("Invoice no.", required=True),
            "delivery_date": st.column_config.DateColumn("Delivery date", required=True),
            "amount": st.column_config.NumberColumn("Invoice amount (₹)", min_value=0, required=True),
            "amount_paid": st.column_config.NumberColumn("Already paid (₹)", min_value=0, default=0),
            "written_agreement": st.column_config.CheckboxColumn(
                "Written credit terms?", default=False,
                help="Unticked = no written agreement, so payment was due in 15 days.",
            ),
            "agreed_credit_days": st.column_config.NumberColumn(
                "Agreed credit days", min_value=0, default=0, help="Capped at 45 by Section 15.",
            ),
        },
    )

    results = []
    for row in invoices_df.dropna(subset=["invoice_no", "delivery_date", "amount"]).itertuples():
        invoice = Invoice(
            invoice_no=str(row.invoice_no),
            delivery_date=pd.Timestamp(row.delivery_date).date(),
            amount=float(row.amount),
            amount_paid=0.0 if pd.isna(row.amount_paid) else float(row.amount_paid),
            agreed_credit_days=int(row.agreed_credit_days or 0) if row.written_agreement else None,
        )
        results.append(evaluate_invoice(invoice, as_of, bank_rate, udyam_date))

    overdue = [r for r in results if r.days_overdue > 0 and r.outstanding > 0]
    principal = sum(r.outstanding for r in overdue)
    interest = sum(r.interest for r in overdue)

    c1, c2, c3 = st.columns(3)
    c1.metric("Overdue principal", f"₹{format_inr(principal)}")
    c2.metric("Statutory interest", f"₹{format_inr(interest)}")
    c3.metric("Total claimable", f"₹{format_inr(principal + interest)}")

    if results:
        table = pd.DataFrame(
            [
                {
                    "Invoice": r.invoice_no,
                    "Due date": r.due_date,
                    "Days overdue": r.days_overdue,
                    "Outstanding (₹)": r.outstanding,
                    "Interest (₹)": r.interest,
                    "Total (₹)": round(r.total_due, 2),
                }
                for r in results
            ]
        )
        money = st.column_config.NumberColumn(format="%.2f")
        st.dataframe(
            table,
            width="stretch",
            hide_index=True,
            column_config={"Outstanding (₹)": money, "Interest (₹)": money, "Total (₹)": money},
        )
        st.download_button(
            "Download interest sheet (CSV)",
            table.to_csv(index=False).encode(),
            file_name=f"interest_{buyer.replace(' ', '_')}_{as_of}.csv",
            mime="text/csv",
        )
        for r in results:
            for warning in r.warnings:
                st.warning(f"{r.invoice_no}: {warning}")

with tab_remind:
    if not overdue:
        st.info("No overdue invoices yet. Add invoices in tab 1.")
    else:
        c1, c2, c3 = st.columns(3)
        language = c1.selectbox("Language", list(LANGUAGES), format_func=LANGUAGES.get)
        tier = c2.selectbox("Escalation stage", list(TIERS), format_func=TIERS.get)
        deadline_days = c3.number_input("Days to pay", min_value=1, max_value=60, value=7)
        offer_waiver = tier == "firm" and st.checkbox(
            "Offer to waive interest if principal is paid on time",
            help="Protects the relationship: the interest figure is leverage, not the goal.",
        )

        message = render(
            language,
            tier,
            offer_waiver=offer_waiver,
            buyer=buyer,
            supplier=supplier,
            udyam=udyam,
            invoices=", ".join(r.invoice_no for r in overdue),
            principal=format_inr(principal),
            interest=format_inr(interest),
            total=format_inr(principal + interest),
            max_days=max(r.days_overdue for r in overdue),
            as_of=as_of.strftime("%d-%m-%Y"),
            deadline_days=deadline_days,
        )
        st.text_area("Message", message, height=320)
        st.link_button("Open in WhatsApp", f"https://wa.me/?text={quote(message)}")
        if language != "en":
            st.caption("Regional templates are fixed drafts: have a native speaker proofread before sending.")

with tab_odr:
    st.subheader("Are you eligible?")
    for item in odr_checklist.ELIGIBILITY:
        st.checkbox(item, key=f"elig_{item}")
    st.subheader("Documents to collect")
    for item in odr_checklist.DOCUMENTS:
        st.checkbox(item, key=f"doc_{item}")
    st.subheader("Filing steps")
    for i, step in enumerate(odr_checklist.STEPS, 1):
        st.markdown(f"{i}. {step}")
    st.link_button("Go to MSME ODR portal", "https://odr.msme.gov.in")

st.divider()
st.caption(
    "Estimates only, not legal advice. Interest assumes one bank rate across the whole period and treats "
    "part payments as made before the due date. The Facilitation Council decides the final amount."
)
