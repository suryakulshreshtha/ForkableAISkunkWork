"""Code generation, including the safety gate on model-authored source."""

from __future__ import annotations

import ast

import pytest

from forkable_ai_agent.agent.generator import TestGenerator, UnsafeGeneratedCode, validate_code
from forkable_ai_agent.agent.memory import Memory
from forkable_ai_agent.agent.planner import Planner

SPEC = """Test: login_happy_path
go to the login page
fill username with demo
fill password with secret123
click log in
should be redirected to /dashboard
should see Welcome
"""


def test_generated_module_is_valid_python(settings, demo_app):
    plan = Planner(settings, None).plan(SPEC, demo_app.base_url)
    generated = TestGenerator(settings).generate(plan)
    tree = ast.parse(generated.code)
    functions = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    assert functions == ["test_login_happy_path"]
    assert "from playwright.sync_api import Page, expect" in generated.code


def test_generator_prefers_semantic_locators_when_nothing_is_proven(settings, demo_app):
    plan = Planner(settings, None).plan(SPEC, demo_app.base_url)
    code = TestGenerator(settings).generate(plan).code
    assert 'get_by_role("textbox", name="username")' in code
    assert "data-testid" not in code


def test_generator_emits_locators_proven_during_a_run(settings, demo_app):
    memory = Memory(settings.path(settings.memory_path))
    memory.record_success("username", "/login", 'testid||0|[data-testid="username"]', "data-testid")
    plan = Planner(settings, None).plan(SPEC, demo_app.base_url)
    code = TestGenerator(settings, memory).generate(plan).code
    # quotes are escaped inside the emitted string literal
    assert r'[data-testid=\"username\"]' in code
    assert "get_by_role" not in code.split("fill")[0].split("page.goto")[-1]


def test_assertions_are_web_first(settings, demo_app):
    plan = Planner(settings, None).plan(SPEC, demo_app.base_url)
    code = TestGenerator(settings).generate(plan).code
    assert "expect(page).to_have_url" in code
    assert "to_contain_text" in code
    assert "sleep" not in code


def test_file_is_written_to_disk(settings, demo_app, tmp_path):
    plan = Planner(settings, None).plan(SPEC, demo_app.base_url)
    generator = TestGenerator(settings)
    generated = generator.generate(plan)
    path = generator.write(generated, tmp_path / "generated")
    assert path.exists() and path.name == "test_login_happy_path.py"


@pytest.mark.parametrize("snippet", [
    "import subprocess\n",
    "import os\nos.system('rm -rf /')\n",
    "eval('1+1')\n",
    "from socket import socket\n",
    "__import__('os')\n",
])
def test_dangerous_generated_code_is_rejected(snippet):
    with pytest.raises(UnsafeGeneratedCode):
        validate_code(snippet)


def test_syntactically_broken_code_is_rejected():
    with pytest.raises(UnsafeGeneratedCode):
        validate_code("def test(:\n  pass")


def test_allowed_imports_pass():
    validate_code("import re\nimport pytest\nfrom playwright.sync_api import Page\n")
