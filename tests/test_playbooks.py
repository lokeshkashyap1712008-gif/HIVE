from hive.playbooks import load_playbook, record_success, record_failure, site_key, save_playbook


def test_record_success_updates_trust_and_flow():
    sk = site_key("https://example.com/login")
    # Reset playbook for clean test
    save_playbook(sk, {"trust_score": 0, "sessions": {}, "login": {}, "signup": {}, "checkout": {}})
    pb0 = load_playbook(sk)
    assert pb0["trust_score"] == 0

    pb1 = record_success(
        sk,
        flow="login",
        session_name="example_com",
        last_url="https://example.com/dashboard",
        trust_delta=8,
        note="ok",
    )

    assert pb1["trust_score"] == 8
    assert pb1["login"]["session_name"] == "example_com"
    assert pb1["login"]["last_url"] == "https://example.com/dashboard"


def test_record_failure_decreases_trust():
    sk = site_key("amazon.com")
    # Reset playbook for clean test
    save_playbook(sk, {"trust_score": 20, "sessions": {}, "login": {}, "signup": {}, "checkout": {}})
    pb0 = load_playbook(sk)
    pb1 = record_failure(sk, flow="checkout", trust_delta=-10)
    assert pb1["trust_score"] == pb0["trust_score"] - 10

