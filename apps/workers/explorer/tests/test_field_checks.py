from explorer_worker.field_checks import FIELD_CHECK, field_checks
from explorer_worker.tests_stage import balanced


def _form(name, fields, kind="form"):
    return {"name": name, "kind": kind, "business_thing": "Lead", "fields": fields}


def test_required_fields_and_recorded_rules_become_scenarios():
    screen = _form(
        "New Lead form",
        [
            {"label": "Last Name", "required": True},
            {"label": "Email", "required": True, "notes": "Must be a valid email address."},
            {
                "label": "Password",
                "required": False,
                "notes": "Must be at least 8 characters long.",
            },
            {"label": "Title", "notes": "Maximum 255 characters."},
            {"label": "Status", "required": False, "notes": "Options are New and Working."},
        ],
    )
    titles = [t["title"] for t in field_checks([screen])]
    assert titles == [
        "Empty New Lead form can't be saved",
        "Last Name is required on New Lead form",
        "Email is required on New Lead form",
        "Email refuses an invalid email on New Lead form",
        "Password refuses fewer than 8 characters on New Lead form",
        # Two rules per form (RULES_PER_FORM): Title's limit is not tried.
    ]
    assert all(
        t["kind"] == "validation" and t["start_screen"] == "New Lead form"
        for t in field_checks([screen])
    )


def test_one_required_field_gets_only_the_empty_form_check_and_login_is_skipped():
    one = _form("New Role form", [{"label": "Role Name", "required": True}])
    login = _form("Login", [{"label": "Password", "required": True}], kind="login")
    layout = _form("Layout editor", [{"label": "Name", "required": True}], kind="settings")
    profile = _form(
        "My profile", [{"label": "New Password", "notes": "Must be at least 8 characters"}]
    )
    assert [t["title"] for t in field_checks([one, login, layout, profile])] == [
        "Empty New Role form can't be saved"
    ]


def test_field_rules_come_on_top_of_the_cap_and_screen_opens_are_trimmed_first():
    opens = [{"kind": "data_load", "coverage": "L-01 Page loads", "start_screen": "Leads"}] * 5
    search = [{"kind": "data_load", "coverage": "L-07 Search match", "start_screen": "Leads"}]
    rules = [{"kind": "validation", "coverage": FIELD_CHECK, "start_screen": "New Lead form"}] * 2
    kept = balanced(opens + search + rules, 2)
    assert [t["coverage"] for t in kept] == [
        FIELD_CHECK,
        FIELD_CHECK,
        "L-07 Search match",
        "L-01 Page loads",
    ]


def test_required_checks_accept_any_way_an_app_says_so_and_ignore_the_star():
    many = [{"label": f"Field {i} *", "required": True} for i in range(5)]
    tests = field_checks([_form("New Contact form", many)])
    titles = [t["title"] for t in tests]
    # The empty form plus two fields left out one at a time (REQUIRED_PER_FORM).
    assert titles == [
        "Empty New Contact form can't be saved",
        "Field 0 is required on New Contact form",
        "Field 1 is required on New Contact form",
    ]
    expected = tests[1]["expected"]
    assert "pop-up that may disappear" in expected and "Please fill out this field" in expected
    assert "Naming only the first missing one is fine" in tests[0]["expected"]


def test_limits_in_the_page_code_become_scenarios_once_each():
    from explorer_worker.field_checks import broken_rules, with_code_limits

    read = [
        {"label": "Amount", "type": "number", "notes": ""},
        {"label": "Email", "type": "text", "notes": "Must be a valid email address."},
        {"label": "Code", "type": "text", "notes": "Maximum 6 characters."},
        {"label": "Close Date", "type": "date", "notes": ""},
    ]
    code = [
        {"label": "Amount *", "type": "number", "min": "0", "max": "1000000", "required": True},
        {"label": "Email", "type": "email"},
        {"label": "Code", "type": "text", "maxlength": "6", "pattern": "[A-Z]+"},
        {"label": "close date", "type": "date", "min": "2026-01-01"},
    ]
    amount, email, short_code, close = with_code_limits(read, code)
    assert amount["required"] is True
    assert [r[:2] for r in broken_rules(amount)] == [
        ("-1", "a value below 0"),
        ("1000001", "a value above 1000000"),
    ]
    assert [r[1] for r in broken_rules(email)] == ["an invalid email"]  # code + notes: one
    assert [r[1] for r in broken_rules(short_code)] == [
        "more than 6 characters",  # maxlength + "Maximum 6 characters": one
        "a value in the wrong format",
    ]
    assert broken_rules(close)[0][0] == "a date before 2026-01-01"
    assert broken_rules({"label": "Notes", "notes": "Options are A and B."}) == []


def test_a_flagged_field_is_a_proof_the_test_caused_and_is_exported():
    from explorer_worker.testkit import playwright_code
    from explorer_worker.tests_stage import proof_was_there_before

    check = {"kind": "field_invalid", "value": "Last Name"}
    # The field's name is on screen from the start; the flag comes from acting.
    assert not proof_was_there_before(check, "New Contact Last Name Email", "https://a/#/New")
    code = playwright_code("t", [], [{"do": "goto", "url": "https://a/#/New"}], check, "")
    assert 'page.getByLabel("Last Name").first().evaluate(' in code
    assert "aria-invalid" in code and "validity.valid" in code
