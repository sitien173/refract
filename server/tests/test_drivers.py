
import pytest

from refract.backends import BackendResult
from refract.config import TargetConfig
from refract.drivers import _normalize, _target_args
from tests.orchestration_helpers import Raised, outcome, plain

TOKEN_KEYS = ("context_used", "context_window", "input", "output", "cache_read", "cache_write")


def test_normalize_preserves_backend_tokens() -> None:
    tokens = dict.fromkeys(TOKEN_KEYS) | {"input": 17}
    result = _normalize(BackendResult(
        outcome="OK",
        SESSION_ID="session",
        agent_messages="done",
        error="",
        error_class="",
        tokens=tokens,
    ))

    assert result.tokens == tokens


def test_driver_result_tokens_default_to_all_unknown() -> None:
    from refract.drivers import DriverResult

    result = DriverResult("SUCCESS", "", "", "", "")

    assert result.tokens == dict.fromkeys(TOKEN_KEYS)


def _target(backend: str, **settings) -> TargetConfig:
    return TargetConfig("t", backend, **settings)


# Characterization of _target_args. Expected values were recorded from the
# implementation before the complexity refactor.
_TARGET_ARGS_CASES = {
    'agy_plain': (
        _target('agy'),
        (),
    ),
    'agy_model': (
        _target('agy', model='m'),
        ('--model', 'm'),
    ),
    'agy_ignores_other_settings': (
        _target('agy', model='m', reasoning='r', system_prompt='s', backend_profile='bp', args=('--x',)),
        ('--x', '--model', 'm'),
    ),
    'codex_plain': (
        _target('codex'),
        (),
    ),
    'codex_profile': (
        _target('codex', backend_profile='bp'),
        ('--profile', 'bp'),
    ),
    'codex_model': (
        _target('codex', model='m'),
        ('--model', 'm'),
    ),
    'codex_profile_model': (
        _target('codex', model='m', backend_profile='bp'),
        ('--profile', 'bp', '--model', 'm', '-c', 'model="m"'),
    ),
    'codex_profile_model_escaped': (
        _target('codex', model='a\\b"c', backend_profile='bp'),
        ('--profile', 'bp', '--model', 'a\\b"c', '-c', 'model="a\\\\b\\"c"'),
    ),
    'codex_model_escaped_without_profile': (
        _target('codex', model='a"b'),
        ('--model', 'a"b'),
    ),
    'codex_reasoning': (
        _target('codex', reasoning='high'),
        ('-c', 'model_reasoning_effort=high'),
    ),
    'codex_all': (
        _target('codex', model='m', reasoning='r', system_prompt='s', backend_profile='bp', args=('--x', 'y')),
        ('--x', 'y', '--profile', 'bp', '--model', 'm', '-c', 'model="m"', '-c', 'model_reasoning_effort=r'),
    ),
    'pi_plain': (
        _target('pi'),
        ('--approve',),
    ),
    'pi_user_args_then_approve': (
        _target('pi', args=('--x',)),
        ('--x', '--approve'),
    ),
    'pi_system_prompt': (
        _target('pi', system_prompt='s'),
        ('--approve', '--system-prompt', 's'),
    ),
    'pi_model': (
        _target('pi', model='m'),
        ('--approve', '--model', 'm'),
    ),
    'pi_reasoning': (
        _target('pi', reasoning='r'),
        ('--approve', '--thinking', 'r'),
    ),
    'pi_all': (
        _target('pi', model='m', reasoning='r', system_prompt='s', backend_profile='bp', args=('--x',)),
        ('--x', '--approve', '--system-prompt', 's', '--model', 'm', '--thinking', 'r'),
    ),
    'claude_plain': (
        _target('claude'),
        (),
    ),
    'claude_system_prompt': (
        _target('claude', system_prompt='s'),
        ('--system-prompt', 's'),
    ),
    'claude_model': (
        _target('claude', model='m'),
        ('--model', 'm'),
    ),
    'claude_reasoning': (
        _target('claude', reasoning='r'),
        ('--effort', 'r'),
    ),
    'claude_all': (
        _target('claude', model='m', reasoning='r', system_prompt='s', backend_profile='bp', args=('--x',)),
        ('--x', '--system-prompt', 's', '--model', 'm', '--effort', 'r'),
    ),
    'unknown_backend_passthrough': (
        _target('other', model='m', reasoning='r', args=('--x',)),
        ('--x',),
    ),
    'args_not_mutated_order': (
        _target('claude', model='m', args=('--model', 'user')),
        ('--model', 'user', '--model', 'm'),
    ),
    'reject_dashdash': (
        _target('codex', args=('--',)),
        Raised(ValueError, "Target 't' args cannot contain the reserved '--' token"),
    ),
    'reject_nul': (
        _target('claude', args=('a\x00',)),
        Raised(ValueError, "Target 't' args cannot contain NUL bytes"),
    ),
    'reject_codex_cd': (
        _target('codex', args=('--cd=/x',)),
        Raised(ValueError, "Codex target 't' args cannot override the workspace root"),
    ),
    'reject_codex_short_c': (
        _target('codex', args=('-Cx',)),
        Raised(ValueError, "Codex target 't' args cannot override the workspace root"),
    ),
    'pi_skill_allowed': (
        _target('pi', args=('--skill=x',)),
        ('--skill=x', '--approve'),
    ),
    'reject_codex_cd_agy_ok': (
        _target('agy', args=('--cd', 'x')),
        ('--cd', 'x'),
    ),
}


@pytest.mark.parametrize("case", list(_TARGET_ARGS_CASES))
def test_target_args_characterization(case) -> None:
    target, expected = _TARGET_ARGS_CASES[case]
    assert outcome(lambda: _target_args(target)) == plain(expected)


def test_target_args_does_not_leak_env_into_argv() -> None:
    target = _target("claude", model="m", env={"SECRET": "value"})
    assert "value" not in _target_args(target)
    assert "SECRET" not in _target_args(target)

