"""Reminder templates, one escalation ladder per language.

To add a state language, add an entry to TEMPLATES with the same tier keys
and placeholders. Have a native speaker proofread before real use.
"""

from __future__ import annotations

TIERS = {
    "friendly": "1 · Friendly reminder",
    "firm": "2 · Firm reminder with statutory interest",
    "final": "3 · Final notice before ODR filing",
}

LANGUAGES = {"en": "English", "mr": "मराठी (Marathi)"}

TEMPLATES = {
    "en": {
        "friendly": (
            "Dear {buyer},\n\n"
            "This is a gentle reminder that our invoice(s) {invoices} totalling ₹{principal} "
            "were due for payment. We would be grateful if you could arrange the payment at the earliest.\n\n"
            "Please ignore this message if the payment has already been made.\n\n"
            "Regards,\n{supplier}"
        ),
        "firm": (
            "Dear {buyer},\n\n"
            "The following invoice(s) remain unpaid: {invoices}. The outstanding amount is ₹{principal}, "
            "overdue by up to {max_days} days.\n\n"
            "{supplier} is a registered micro/small enterprise (Udyam No. {udyam}). Under Sections 15 and 16 "
            "of the MSMED Act, 2006, payments delayed beyond the agreed period (maximum 45 days) attract "
            "compound interest with monthly rests at three times the RBI bank rate. As of {as_of}, the interest "
            "accrued is approximately ₹{interest}, making the total due ₹{total}.\n\n"
            "We request you to clear the outstanding amount within {deadline_days} days.{waiver}\n\n"
            "Regards,\n{supplier}"
        ),
        "final": (
            "Subject: Final notice for overdue payment\n\n"
            "Dear {buyer},\n\n"
            "Despite our earlier reminders, payment against invoice(s) {invoices} has not been received. "
            "As of {as_of}, the amount due is ₹{total}, comprising principal of ₹{principal} and interest of "
            "₹{interest} under Section 16 of the MSMED Act, 2006.\n\n"
            "If this amount is not received within {deadline_days} days, we will be constrained to file a "
            "reference before the Micro and Small Enterprises Facilitation Council under Section 18 of the "
            "MSMED Act through the MSME ODR portal (odr.msme.gov.in), without further notice.\n\n"
            "{supplier}\nUdyam No. {udyam}"
        ),
        "waiver": " If the principal of ₹{principal} is received within {deadline_days} days, we will not claim the interest.",
    },
    "mr": {
        "friendly": (
            "नमस्कार {buyer},\n\n"
            "आमच्या बीजक क्रमांक {invoices} ची एकूण ₹{principal} इतकी रक्कम देय झाली आहे, "
            "याची आम्ही आपल्याला नम्रपणे आठवण करून देत आहोत. कृपया लवकरात लवकर रक्कम अदा करावी.\n\n"
            "आपण आधीच रक्कम भरली असल्यास कृपया या संदेशाकडे दुर्लक्ष करावे.\n\n"
            "धन्यवाद,\n{supplier}"
        ),
        "firm": (
            "नमस्कार {buyer},\n\n"
            "आमची पुढील बीजके अद्याप थकीत आहेत: {invoices}. एकूण थकबाकी ₹{principal} असून ती "
            "{max_days} दिवसांपर्यंत उशिरा आहे.\n\n"
            "{supplier} हा नोंदणीकृत सूक्ष्म/लघु उद्योग आहे (उद्यम क्र. {udyam}). सूक्ष्म, लघु आणि मध्यम "
            "उद्योग विकास अधिनियम, 2006 च्या कलम 15 आणि 16 नुसार, मान्य मुदतीनंतर (कमाल 45 दिवस) "
            "न भरलेल्या रकमेवर रिझर्व्ह बँकेच्या बँक दराच्या तिप्पट दराने मासिक चक्रवाढ व्याज लागू होते. "
            "{as_of} पर्यंत हे व्याज अंदाजे ₹{interest} असून एकूण देय रक्कम ₹{total} आहे.\n\n"
            "कृपया {deadline_days} दिवसांच्या आत थकबाकी रक्कम अदा करावी.{waiver}\n\n"
            "धन्यवाद,\n{supplier}"
        ),
        "final": (
            "विषय: थकीत देयकाबाबत अंतिम सूचना\n\n"
            "{buyer},\n\n"
            "वारंवार आठवण करूनही आमच्या बीजक क्रमांक {invoices} ची रक्कम अद्याप मिळालेली नाही. "
            "{as_of} पर्यंत मूळ रक्कम ₹{principal} आणि MSMED अधिनियम, 2006 च्या कलम 16 नुसार "
            "व्याज ₹{interest} असे एकूण ₹{total} देय आहे.\n\n"
            "ही रक्कम {deadline_days} दिवसांच्या आत न मिळाल्यास, आम्हाला पुढील सूचना न देता MSMED "
            "अधिनियमाच्या कलम 18 अंतर्गत MSME ODR पोर्टलद्वारे (odr.msme.gov.in) सूक्ष्म व लघु उद्योग "
            "सुविधा परिषदेकडे प्रकरण दाखल करावे लागेल.\n\n"
            "{supplier}\nउद्यम क्र. {udyam}"
        ),
        "waiver": " मूळ रक्कम ₹{principal} जर {deadline_days} दिवसांच्या आत मिळाली, तर आम्ही व्याजाचा दावा करणार नाही.",
    },
}


def render(language: str, tier: str, *, offer_waiver: bool = False, **fields) -> str:
    templates = TEMPLATES[language]
    waiver = templates["waiver"].format(**fields) if offer_waiver and tier == "firm" else ""
    return templates[tier].format(waiver=waiver, **fields)
