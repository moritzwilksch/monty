import pytest
from inline_snapshot import snapshot

import pydantic_monty


def test_repl_create_feed_stateful():
    repl, output = pydantic_monty.MontyRepl.create('counter = 0')

    assert output == snapshot(None)
    assert repl.feed('counter = counter + 1') == snapshot(None)
    assert repl.feed('counter') == snapshot(1)


def test_repl_dump_load_roundtrip():
    repl, _ = pydantic_monty.MontyRepl.create('x = 40')

    assert repl.feed('x = x + 1') == snapshot(None)

    serialized = repl.dump()
    loaded = pydantic_monty.MontyRepl.load(serialized)

    assert loaded.feed('x + 1') == snapshot(42)


def test_repl_create_with_start_inputs_feed_stateful():
    repl, output = pydantic_monty.MontyRepl.create(
        'counter = start',
        inputs=['start'],
        start_inputs={'start': 0},
    )

    assert output == snapshot(None)
    assert repl.feed('counter = counter + 1') == snapshot(None)
    assert repl.feed('counter') == snapshot(1)


def test_repl_feed_start_resume_keeps_state():
    repl, _ = pydantic_monty.MontyRepl.create('counter = 1')

    progress = repl.feed_start('counter = increment(counter)\ncounter')
    assert isinstance(progress, pydantic_monty.FunctionSnapshot)
    assert progress.function_name == snapshot('increment')
    assert progress.args == snapshot((1,))

    result = progress.resume(return_value=2)
    assert isinstance(result, pydantic_monty.MontyComplete)
    assert result.output == snapshot(2)
    assert repl.feed('counter') == snapshot(2)


def test_repl_feed_start_name_lookup_resume_keeps_state():
    repl, _ = pydantic_monty.MontyRepl.create('')

    progress = repl.feed_start('value = thing\nvalue')
    assert isinstance(progress, pydantic_monty.NameLookupSnapshot)
    assert progress.variable_name == snapshot('thing')

    result = progress.resume(value=42)
    assert isinstance(result, pydantic_monty.MontyComplete)
    assert result.output == snapshot(42)
    assert repl.feed('value') == snapshot(42)


def test_repl_feed_start_blocks_other_snippets_while_suspended():
    repl, _ = pydantic_monty.MontyRepl.create('')

    progress = repl.feed_start('call_me()')
    assert isinstance(progress, pydantic_monty.FunctionSnapshot)

    with pytest.raises(RuntimeError) as exc_info:
        repl.feed('1')
    assert exc_info.value.args[0] == snapshot('REPL session is currently executing another snippet')

    result = progress.resume(return_value=None)
    assert isinstance(result, pydantic_monty.MontyComplete)
    assert result.output is None
    assert repl.feed('1') == snapshot(1)


def test_repl_feed_start_external_function_filter_raises_name_error():
    repl, _ = pydantic_monty.MontyRepl.create('')

    with pytest.raises(pydantic_monty.MontyRuntimeError) as exc_info:
        repl.feed_start('missing()', external_functions=['other'])

    inner = exc_info.value.exception()
    assert type(inner) is NameError
    assert str(inner) == snapshot("name 'missing' is not defined")


def test_repl_feed_start_type_check_stubs():
    repl, _ = pydantic_monty.MontyRepl.create('')

    with pytest.raises(pydantic_monty.MontyTypingError) as exc_info:
        repl.feed_start(
            'tool("x")',
            external_functions=['tool'],
            type_check_stubs='def tool(value: int) -> int: ...',
        )

    assert str(exc_info.value) == snapshot("""\
error[invalid-argument-type]: Argument to function call is incorrect
 --> main.py:1:6
  |
1 | tool("x")
  |      ^^^ Expected `int`, found `Literal["x"]`
  |
info: Function defined here
 --> type_stubs.pyi:1:5
  |
1 | def tool(value: int) -> int: ...
  |     ----
""")
