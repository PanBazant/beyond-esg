import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from codex_run_lib import select_stratified_sample
from codex_run_lib import parse_openclaw_response


def _row(symbol, category, coverage, error=False):
    return {"symbol": symbol, "category": category,
            "axiological_coverage": coverage, "error": error}


def test_sample_is_deterministic_with_seed():
    rows = [_row(f"S{i}", f"Cat{i % 4}", "present" if i % 2 else "none") for i in range(200)]
    a = select_stratified_sample(rows, target_n=40, seed=42)
    b = select_stratified_sample(rows, target_n=40, seed=42)
    assert a == b
    assert len(a) == 40


def test_sample_skips_error_rows():
    rows = [_row(f"E{i}", "Cat0", "error", error=True) for i in range(10)]
    rows += [_row(f"G{i}", "Cat0", "present") for i in range(10)]
    sample = select_stratified_sample(rows, target_n=10, seed=1)
    assert all(s.startswith("G") for s in sample)


def test_sample_spans_multiple_categories():
    rows = [_row(f"A{i}", "CatA", "present") for i in range(50)]
    rows += [_row(f"B{i}", "CatB", "none") for i in range(50)]
    sample = select_stratified_sample(rows, target_n=20, seed=7)
    cats = {s[0] for s in sample}  # 'A' lub 'B'
    assert cats == {"A", "B"}  # obie warstwy reprezentowane


def test_sample_returns_all_when_target_exceeds_population():
    rows = [_row(f"S{i}", "Cat0", "present") for i in range(5)]
    sample = select_stratified_sample(rows, target_n=100, seed=1)
    assert len(sample) == 5


def test_parse_extracts_json_from_payload_text():
    inner = '{"frames": [{"label": "regulatory scrutiny", "evidence": "SEC", "exposure": "high", "sentiment": "negative"}], "axiological_coverage": "present", "notes": null}'
    stdout = json.dumps({"status": "ok", "result": {"payloads": [{"text": inner, "mediaUrl": None}]}})
    parsed = parse_openclaw_response(stdout)
    assert parsed["axiological_coverage"] == "present"
    assert parsed["frames"][0]["label"] == "regulatory scrutiny"


def test_parse_extracts_json_from_flat_payloads():
    # ścieżka embedded fallback OpenClaw: brak zawijania w "result"
    inner = '{"frames": [], "axiological_coverage": "present", "notes": null}'
    stdout = json.dumps({"payloads": [{"text": inner, "mediaUrl": None}], "meta": {}})
    parsed = parse_openclaw_response(stdout)
    assert parsed["axiological_coverage"] == "present"


def test_parse_skips_leading_noise_before_json():
    inner = '{"frames": [], "axiological_coverage": "none", "notes": null}'
    stdout = "Gateway agent failed; falling back to embedded\n" + \
        json.dumps({"payloads": [{"text": inner}]})
    parsed = parse_openclaw_response(stdout)
    assert parsed["axiological_coverage"] == "none"


def test_parse_handles_text_around_json():
    inner = 'Here is the result:\n{"frames": [], "axiological_coverage": "none", "notes": null}\nDone.'
    stdout = json.dumps({"result": {"payloads": [{"text": inner}]}})
    parsed = parse_openclaw_response(stdout)
    assert parsed["frames"] == []
    assert parsed["axiological_coverage"] == "none"


def test_parse_returns_none_on_empty_payloads():
    stdout = json.dumps({"status": "ok", "result": {"payloads": []}})
    assert parse_openclaw_response(stdout) is None


def test_parse_returns_none_on_garbage_stdout():
    assert parse_openclaw_response("not json at all") is None


def test_parse_returns_none_when_payload_text_has_no_json():
    stdout = json.dumps({"result": {"payloads": [{"text": "sorry, no answer"}]}})
    assert parse_openclaw_response(stdout) is None


from codex_run_lib import build_openclaw_cmd


def test_build_cmd_has_wsl_agent_and_thinking():
    cmd = build_openclaw_cmd("ACME", "PROMPT TEXT", agent="profiler", thinking="low")
    assert cmd[0] == "wsl"
    assert "Ubuntu-24.04" in cmd
    assert "/home/macie/.npm-global/bin/openclaw" in cmd
    assert "--agent" in cmd and "profiler" in cmd
    # effort pinowany jawnie (wipe sesji kasuje ustawiony thinkingLevel)
    th_i = cmd.index("--thinking")
    assert cmd[th_i + 1] == "low"
    # prompt jako argument --message
    msg_i = cmd.index("--message")
    assert cmd[msg_i + 1] == "PROMPT TEXT"
    assert "--json" in cmd


def test_build_cmd_strips_control_chars_from_prompt():
    # NUL i inne znaki kontrolne psują CreateProcess na Windows
    cmd = build_openclaw_cmd("X", "abc\x00def\x07\nok `code` end", agent="profiler")
    msg = cmd[cmd.index("--message") + 1]
    assert "\x00" not in msg and "\x07" not in msg
    assert "`" not in msg  # backtick usuniety (psuje powloke w WSL)
    assert "abcdef" in msg and "\nok" in msg  # \n zachowany


def test_build_cmd_drops_ignored_session_id():
    # --agent wymusza klucz agent:<id>:main, wiec --session-id i tak byl ignorowany;
    # izolacje daje wipe sesji (build_wipe_cmd), nie --session-id.
    cmd = build_openclaw_cmd("ACME", "P", agent="profiler")
    assert "--session-id" not in cmd


def test_build_wipe_cmd_targets_profiler_sessions():
    from codex_run_lib import build_wipe_cmd
    cmd = build_wipe_cmd(agent="profiler")
    assert cmd[0] == "wsl"
    joined = " ".join(cmd)
    assert "rm -f" in joined
    assert "agents/profiler/sessions" in joined
