from hive.playbooks import load_playbook, record_success, site_key


def test_record_success_updates_trust_and_flow():
    sk = site_key("https://example.com/login")
    pb0 = load_playbook(sk)
    assert pb0.get("trust_score", 0) >= 0

    pb1 = record_success(
        sk,
        flow="login",
        session_name="example_com",
        last_url="https://example.com/dashboard",
        trust_delta=8,
        note="ok",
    )

    assert pb1["trust_score"] == pb0["trust_score"] + 8
    assert pb1["login"]["session_name"] == "example_com"
    assert pb1["login"]["last_url"] == "https://example.com/dashboard"


def test_record_failure_decreases_trust():
    sk = site_key("amazon.com")
    pb0 = load_playbook(sk)
    pb1 = record_success(
        sk, flow="checkout", session_name="amazon_com", last_url="https://amazon.com", trust_delta=8
    )
    pb2 = record_success(
        sk, flow="checkout", session_name="amazon_com", last_url="https://amazon.com", trust_delta=-10, note="fail"
    )
    assert pb2["trust_score"] <= pb1["trust_score"]

