import os
import tempfile
import textwrap

import pytest
import yaml

from cimulator.cli import main
from cimulator.inputs import InputsError
from cimulator.loader import load_and_resolve, load_yaml


def write(directory, name, contents):
    path = os.path.join(directory, name)
    with open(path, "w") as f:
        f.write(textwrap.dedent(contents))
    return path


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


HEADER = """\
spec:
  inputs:
    version:
      default: ""
    tier:
      options: [bronze, gold]
      default: bronze
    needs_list:
      type: array
      default: [build]
    enabled:
      type: boolean
      default: false
    retries:
      type: number
      default: 2
---
"""


def test_header_is_dropped_and_defaults_applied(tmp_dir):
    path = write(tmp_dir, ".gitlab-ci.yml", HEADER + """\
variables:
  VERSION: $[[ inputs.version ]]
  TIER: "$[[ inputs.tier ]]"
job:
  script: echo
""")
    config = load_yaml(path)
    assert "spec" not in config
    assert config["variables"] == {"VERSION": "", "TIER": "bronze"}


def test_typed_values_replace_whole_scalars(tmp_dir):
    path = write(tmp_dir, ".gitlab-ci.yml", HEADER + """\
job:
  needs: $[[ inputs.needs_list ]]
  allow_failure: $[[ inputs.enabled ]]
  retry: $[[ inputs.retries ]]
  script: echo retry $[[ inputs.retries ]] enabled $[[ inputs.enabled ]]
""")
    job = load_yaml(path)["job"]
    assert job["needs"] == ["build"]
    assert job["allow_failure"] is False
    assert job["retry"] == 2
    assert job["script"] == "echo retry 2 enabled false"


def test_interpolation_in_keys(tmp_dir):
    path = write(tmp_dir, ".gitlab-ci.yml", HEADER + """\
"$[[ inputs.tier ]]:job":
  script: echo
""")
    assert "bronze:job" in load_yaml(path)


def test_provided_inputs_override_defaults_and_are_coerced(tmp_dir):
    path = write(tmp_dir, ".gitlab-ci.yml", HEADER + """\
variables:
  VERSION: $[[ inputs.version ]]
job:
  needs: $[[ inputs.needs_list ]]
  allow_failure: $[[ inputs.enabled ]]
  retry: $[[ inputs.retries ]]
""")
    config = load_yaml(path, inputs={
        "version": "1.0",  # stays a string, not a float
        "needs_list": "[a, b]",
        "enabled": "true",
        "retries": "1",
    })
    assert config["variables"]["VERSION"] == "1.0"
    assert config["job"] == {"needs": ["a", "b"], "allow_failure": True, "retry": 1}


def test_missing_required_input(tmp_dir):
    path = write(tmp_dir, ".gitlab-ci.yml", """\
spec:
  inputs:
    version:
---
job:
  script: echo $[[ inputs.version ]]
""")
    with pytest.raises(InputsError, match="version"):
        load_yaml(path)
    assert load_yaml(path, inputs={"version": "2"})["job"]["script"] == "echo 2"


def test_null_default_is_required(tmp_dir):
    path = write(tmp_dir, ".gitlab-ci.yml", """\
spec:
  inputs:
    version:
      default: null
---
job:
  script: echo $[[ inputs.version ]]
""")
    with pytest.raises(InputsError, match="version"):
        load_yaml(path)


def test_unknown_provided_input(tmp_dir):
    path = write(tmp_dir, ".gitlab-ci.yml", HEADER + "job:\n  script: echo\n")
    with pytest.raises(InputsError, match="nope"):
        load_yaml(path, inputs={"nope": "x"})


def test_undeclared_input_reference(tmp_dir):
    path = write(tmp_dir, ".gitlab-ci.yml", HEADER + "job:\n  script: echo $[[ inputs.nope ]]\n")
    with pytest.raises(InputsError, match="nope"):
        load_yaml(path)


def test_options_and_regex_are_enforced(tmp_dir):
    path = write(tmp_dir, ".gitlab-ci.yml", """\
spec:
  inputs:
    tier:
      options: [bronze, gold]
      default: bronze
    version:
      regex: ^\\d+\\.\\d+\\.\\d+$
      default: 1.0.0
---
job:
  script: echo
""")
    with pytest.raises(InputsError, match="tier"):
        load_yaml(path, inputs={"tier": "silver"})
    with pytest.raises(InputsError, match="version"):
        load_yaml(path, inputs={"version": "1.0"})
    load_yaml(path, inputs={"tier": "gold", "version": "1.2.3"})


def test_type_mismatch(tmp_dir):
    path = write(tmp_dir, ".gitlab-ci.yml", HEADER + "job:\n  script: echo\n")
    with pytest.raises(InputsError, match="retries"):
        load_yaml(path, inputs={"retries": "many"})


def test_functions(tmp_dir):
    path = write(tmp_dir, ".gitlab-ci.yml", """\
spec:
  inputs:
    name:
      default: "a b'c"
    path:
      default: $CI_PROJECT_DIR/out
---
job:
  variables:
    SHORT: $[[ inputs.name | truncate(0,3) ]]
    QUOTED: $[[ inputs.name | posix_escape ]]
    EXPANDED: $[[ inputs.path | expand_vars ]]
    CHAINED: $[[ inputs.name | truncate(2,3) | posix_escape ]]
""")
    variables = load_yaml(path)["job"]["variables"]
    assert variables["SHORT"] == "a b"
    assert variables["QUOTED"] == "a\\ b\\'c"
    assert variables["EXPANDED"] == "$CI_PROJECT_DIR/out"
    assert variables["CHAINED"] == "b\\'c"


def test_file_without_header_is_left_untouched(tmp_dir):
    path = write(tmp_dir, ".gitlab-ci.yml", "job:\n  script: echo $[[ inputs.x ]]\n")
    assert load_yaml(path)["job"]["script"] == "echo $[[ inputs.x ]]"


def test_inputs_without_header_are_rejected(tmp_dir):
    path = write(tmp_dir, ".gitlab-ci.yml", "job:\n  script: echo\n")
    with pytest.raises(InputsError):
        load_yaml(path, inputs={"x": "1"})


def test_other_interpolation_contexts_are_left_untouched(tmp_dir):
    path = write(tmp_dir, ".gitlab-ci.yml", HEADER + "job:\n  image: reg/img:$[[ component.sha ]]\n")
    assert load_yaml(path)["job"]["image"] == "reg/img:$[[ component.sha ]]"


def test_multiple_documents_without_spec_are_rejected(tmp_dir):
    path = write(tmp_dir, ".gitlab-ci.yml", "a: 1\n---\nb: 2\n")
    with pytest.raises(InputsError):
        load_yaml(path)


def test_header_only_file(tmp_dir):
    path = write(tmp_dir, ".gitlab-ci.yml", HEADER)
    assert load_yaml(path) == {}


def test_include_with_inputs(tmp_dir):
    write(tmp_dir, "template.yml", """\
spec:
  inputs:
    stage:
      default: test
    prefix:
---
"$[[ inputs.prefix ]]-job":
  stage: $[[ inputs.stage ]]
  script: echo
""")
    root = write(tmp_dir, ".gitlab-ci.yml", HEADER + """\
include:
  - local: template.yml
    inputs:
      prefix: $[[ inputs.tier ]]
root:
  script: echo
""")
    config, _ = load_and_resolve(root, inputs={"tier": "gold"})
    assert config["gold-job"] == {"stage": "test", "script": "echo"}


def test_include_input_errors_are_not_swallowed(tmp_dir):
    write(tmp_dir, "template.yml", "spec:\n  inputs:\n    prefix:\n---\njob:\n  script: echo\n")
    root = write(tmp_dir, ".gitlab-ci.yml", "include:\n  - local: template.yml\n")
    with pytest.raises(InputsError, match="prefix"):
        load_and_resolve(root)


def test_simulate_cli_with_inputs(tmp_dir, monkeypatch, capsys):
    ci_file = write(tmp_dir, ".gitlab-ci.yml", HEADER + """\
variables:
  VERSION: $[[ inputs.version ]]
workflow:
  rules:
    - if: $CI_PIPELINE_SOURCE == "web"
release:
  rules:
    - if: $VERSION
  script: echo $[[ inputs.tier ]]
""")
    profiles = write(tmp_dir, "profiles.yml", "web:\n  CI_PIPELINE_SOURCE: web\n")
    output = os.path.join(tmp_dir, "out.yml")

    def simulate(*extra):
        monkeypatch.setattr("sys.argv", ["cli.py", "simulate", ci_file, profiles, "web", "-o", output, *extra])
        main()
        with open(output) as f:
            return yaml.safe_load(f)

    assert simulate()["jobs_list"] == []
    result = simulate("--input", "version=1.2.3", "--input", "tier=gold")
    assert result["jobs_list"] == ["release"]
    assert result["jobs"]["release"]["script"] == "echo gold"

    with pytest.raises(SystemExit):
        simulate("--input", "tier=silver")
    assert "tier" in capsys.readouterr().err


def test_validate_cli_rejects_malformed_input(tmp_dir, monkeypatch, capsys):
    ci_file = write(tmp_dir, ".gitlab-ci.yml", HEADER + "job:\n  script: echo\n")
    monkeypatch.setattr("sys.argv", ["cli.py", "validate", ci_file, "--input", "novalue"])
    with pytest.raises(SystemExit):
        main()
    assert "KEY=VALUE" in capsys.readouterr().err
