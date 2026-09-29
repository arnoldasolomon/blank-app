"""Starting data for the tracker. Only used when no saved tracker file exists yet.

Everything here is editable from the app; the tasks are a first cut to get moving,
not a finished plan.
"""

CASHFLOW = "cashflow"

SEED = {
    "rev": 0,
    "workstreams": [
        {
            "id": "nifty",
            "name": "Nifty lots",
            "goal": "Build up to trading 4 Nifty lots.",
            "status": "Active",
            "priority": "High",
            "owner": "",
            "next_action": "Write down capital per lot and max loss per day before adding size.",
            "metric": {"label": "Lots", "current": 0, "target": 4},
            "feeds": [],
            "risks": "4 lots is real leverage. Scale 1 -> 4 only after the rules have held "
            "over a run of journaled trades.",
            "tasks": [
                {"task": "Define '4 lots': futures or options, capital needed per lot", "done": False, "owner": "", "due": None},
                {"task": "Write trading rules: entry, exit, stop, max daily loss", "done": False, "owner": "", "due": None},
                {"task": "Journal every trade (setup, size, result, mistake)", "done": False, "owner": "", "due": None},
                {"task": "Scale from 1 lot to 4 only after rules hold", "done": False, "owner": "", "due": None},
            ],
        },
        {
            "id": "sir",
            "name": "Sir's job",
            "goal": "Help Sir make money (if he makes money, we make money): advisory dashboard, "
            "market-data product, short-term trading.",
            "status": "Researching",
            "priority": "High",
            "owner": "",
            "next_action": "Map exactly how Sir earns today and where a dashboard adds money.",
            "metric": {"label": "Paying users", "current": 0, "target": 0},
            "feeds": [CASHFLOW, "nifty"],
            "risks": "Selling trading advice/tips in India needs SEBI Research Analyst or Investment "
            "Adviser registration. Redistributing NSE/BSE market data needs an exchange data licence. "
            "Check both before charging anyone.",
            "tasks": [
                {"task": "Map Sir's current income sources", "done": False, "owner": "", "due": None},
                {"task": "Check SEBI RA/IA registration and exchange data-licence requirements", "done": False, "owner": "", "due": None},
                {"task": "Scope advisory dashboard MVP (what data, what advice, who pays)", "done": False, "owner": "", "due": None},
                {"task": "Agree our revenue share with Sir", "done": False, "owner": "", "due": None},
            ],
        },
        {
            "id": "reselling",
            "name": "Reselling",
            "goal": "Pick products to resell, backed by real-world analysis from LinkedIn and X.",
            "status": "Researching",
            "priority": "Medium",
            "owner": "",
            "next_action": "Run the LinkedIn and X analysis on the initial product list.",
            "metric": {"label": "Products shortlisted", "current": 0, "target": 3},
            "feeds": ["gtm"],
            "risks": "",
            "tasks": [
                {"task": "Derive initial product list and research", "done": True, "owner": "", "due": None},
                {"task": "LinkedIn real-world analysis", "done": False, "owner": "", "due": None},
                {"task": "X (Twitter) real-world analysis", "done": False, "owner": "", "due": None},
                {"task": "Shortlist top 3 products with margin and demand numbers", "done": False, "owner": "", "due": None},
            ],
        },
        {
            "id": "gtm",
            "name": "GTM",
            "goal": "Turn the work into a source of cashflow.",
            "status": "Idea",
            "priority": "High",
            "owner": "",
            "next_action": "Decide which workstream GTM is for first and set a monthly cashflow target.",
            "metric": {"label": "Monthly cashflow (Rs)", "current": 0, "target": 0},
            "feeds": [CASHFLOW],
            "risks": "",
            "tasks": [
                {"task": "Pick the first product/offer to sell", "done": False, "owner": "", "due": None},
                {"task": "Pricing and unit economics", "done": False, "owner": "", "due": None},
                {"task": "Pick 1-2 sales channels", "done": False, "owner": "", "due": None},
                {"task": "Land first 10 customers", "done": False, "owner": "", "due": None},
            ],
        },
        {
            "id": "ai_app",
            "name": "AI app / website",
            "goal": "Find bottlenecks in India or the world that AI can solve at very low cost.",
            "status": "Researching",
            "priority": "Medium",
            "owner": "",
            "next_action": "List 20 bottlenecks, then score them.",
            "metric": {"label": "Bottlenecks listed", "current": 0, "target": 20},
            "feeds": [CASHFLOW],
            "risks": "",
            "tasks": [
                {"task": "List bottlenecks (India and global)", "done": False, "owner": "", "due": None},
                {"task": "Score each: pain, willingness to pay, cost to build", "done": False, "owner": "", "due": None},
                {"task": "Validate the top one with 10 real user conversations", "done": False, "owner": "", "due": None},
                {"task": "Build a low-cost MVP", "done": False, "owner": "", "due": None},
            ],
        },
        {
            "id": "youtube",
            "name": "YouTube channel",
            "goal": "Channel (parked for now).",
            "status": "On hold",
            "priority": "Low",
            "owner": "",
            "next_action": "",
            "metric": {"label": "Videos", "current": 0, "target": 0},
            "feeds": [CASHFLOW],
            "risks": "",
            "tasks": [
                {"task": "Decide niche when un-parked", "done": False, "owner": "", "due": None},
            ],
        },
    ],
    "log": [],
}
