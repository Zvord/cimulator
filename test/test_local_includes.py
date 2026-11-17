import json

import pytest
from pathlib import Path

from cimulator.loader import include_rules_match, load_and_resolve


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return str(path)


def test_missing_local_include_fails(tmp_path):
    root = write(tmp_path / ".gitlab-ci.yml", "include:\n  - ci/missing.yml\njob:\n  script: [echo]\n")
    with pytest.raises(ValueError, match="'ci/missing.yml' does not exist"):
        load_and_resolve(root)


def test_invalid_yaml_in_a_local_include_fails(tmp_path):
    write(tmp_path / "ci" / "jobs.yml", "job:\n  script: [echo\n")
    root = write(tmp_path / ".gitlab-ci.yml", "include:\n  - local: ci/jobs.yml\n")
    with pytest.raises(ValueError, match="Error processing include"):
        load_and_resolve(root)


def test_error_in_a_nested_include_fails(tmp_path):
    write(tmp_path / "ci" / "jobs.yml", "include: ci/missing.yml\n")
    root = write(tmp_path / ".gitlab-ci.yml", "include: ci/jobs.yml\n")
    with pytest.raises(ValueError, match="'ci/missing.yml' does not exist"):
        load_and_resolve(root)


def test_local_include_with_a_leading_slash(tmp_path):
    write(tmp_path / "ci" / "jobs.yml", "job:\n  script: [echo]\n")
    root = write(tmp_path / ".gitlab-ci.yml", "include:\n  - /ci/jobs.yml\n  - local: /ci/jobs.yml\n")
    config, _ = load_and_resolve(root)
    assert "job" in config


def test_local_include_with_wildcards(tmp_path):
    write(tmp_path / "ci" / "a.yml", "job_a:\n  script: [echo]\n")
    write(tmp_path / "ci" / "sub" / "b.yml", "job_b:\n  script: [echo]\n")
    root = write(tmp_path / ".gitlab-ci.yml", "include: ci/*.yml\n")
    config, _ = load_and_resolve(root)
    assert "job_a" in config and "job_b" not in config

    root = write(tmp_path / ".gitlab-ci.yml", "include: ci/**.yml\n")
    config, _ = load_and_resolve(root)
    assert "job_a" in config and "job_b" in config


def test_non_local_includes_are_skipped(tmp_path):
    root = write(tmp_path / ".gitlab-ci.yml", """
include:
  - https://example.com/ci.yml
  - remote: https://example.com/ci.yml
  - project: group/project
    file: ci.yml
  - template: Workflows/MergeRequest-Pipelines.gitlab-ci.yml
  - component: example.com/group/component@1.0
job:
  script: [echo]
""")
    config, _ = load_and_resolve(root)
    assert "job" in config


class TestIncludeRules:
    ROOT = """
include:
  - local: ci/$CI_PIPELINE_SOURCE.yml
    rules:
      - if: $CI_PIPELINE_SOURCE == "push"
      - if: $CI_PIPELINE_SOURCE == "web"
        when: never
job:
  script: [echo]
"""

    def test_rules_that_do_not_match_skip_the_include(self, tmp_path):
        # Even a missing file: GitLab only loads the includes its rules keep
        root = write(tmp_path / ".gitlab-ci.yml", self.ROOT)
        for source in ("web", "schedule"):
            config, _ = load_and_resolve(root, variables={"CI_PIPELINE_SOURCE": source})
            assert set(config) == {"job"}

    def test_rules_that_match_load_the_include(self, tmp_path):
        write(tmp_path / "ci" / "push.yml", "push_job:\n  script: [echo]\n")
        root = write(tmp_path / ".gitlab-ci.yml", self.ROOT)
        config, _ = load_and_resolve(root, variables={"CI_PIPELINE_SOURCE": "push"})
        assert "push_job" in config

    def test_missing_file_kept_by_its_rules_fails(self, tmp_path):
        root = write(tmp_path / ".gitlab-ci.yml", self.ROOT)
        with pytest.raises(ValueError, match="'ci/push.yml' does not exist"):
            load_and_resolve(root, variables={"CI_PIPELINE_SOURCE": "push"})

    def test_exists(self, tmp_path):
        write(tmp_path / "ci" / "jobs.yml", "included_job:\n  script: [echo]\n")
        root = write(tmp_path / ".gitlab-ci.yml", """
include:
  - local: ci/jobs.yml
    rules:
      - exists: [Makefile]
job:
  script: [echo]
""")
        config, _ = load_and_resolve(root, variables={})
        assert "included_job" not in config
        write(tmp_path / "Makefile", "")
        config, _ = load_and_resolve(root, variables={})
        assert "included_job" in config

    def test_without_variables_a_missing_file_is_skipped(self, tmp_path, caplog):
        # validate has no profile: whether the include is kept is unknown
        root = write(tmp_path / ".gitlab-ci.yml", self.ROOT)
        config, _ = load_and_resolve(root)
        assert set(config) == {"job"}
        assert "only known when simulating" in caplog.text


class TestVariablesInPaths:
    def test_variables_are_expanded(self, tmp_path):
        write(tmp_path / "ci" / "push.yml", "push_job:\n  script: [echo]\n")
        root = write(tmp_path / ".gitlab-ci.yml", "include: ci/${CI_PIPELINE_SOURCE}.yml\n")
        config, _ = load_and_resolve(root, variables={"CI_PIPELINE_SOURCE": "push"})
        assert "push_job" in config

    def test_undefined_variables_are_empty(self, tmp_path):
        write(tmp_path / "ci" / "jobs.yml", "job:\n  script: [echo]\n")
        root = write(tmp_path / ".gitlab-ci.yml", "include: ci/jobs${UNDEFINED}.yml\n")
        config, _ = load_and_resolve(root, variables={})
        assert "job" in config

    def test_configuration_variables_are_not_used(self, tmp_path):
        # As in GitLab: only predefined, project and pipeline variables
        write(tmp_path / "ci" / "jobs.yml", "job:\n  script: [echo]\n")
        root = write(tmp_path / ".gitlab-ci.yml", "variables:\n  NAME: jobs\ninclude: ci/${NAME}.yml\n")
        with pytest.raises(ValueError, match="does not have a YAML extension|does not exist"):
            load_and_resolve(root, variables={})

    def test_without_variables_a_missing_file_is_skipped(self, tmp_path, caplog):
        root = write(tmp_path / ".gitlab-ci.yml", "include: ci/${CI_PIPELINE_SOURCE}.yml\njob:\n  script: [echo]\n")
        config, _ = load_and_resolve(root)
        assert set(config) == {"job"}
        assert "only known when simulating" in caplog.text


@pytest.mark.parametrize("local", ["[ci/jobs.yml]", "", "~"])
def test_local_that_is_not_a_path_fails(tmp_path, local):
    root = write(tmp_path / ".gitlab-ci.yml", f"include:\n  - local: {local}\n")
    with pytest.raises(ValueError, match="'local' must be the path of a file"):
        load_and_resolve(root)


@pytest.mark.parametrize("content", ["", "# only a comment\n"])
def test_empty_included_file_fails(tmp_path, content):
    write(tmp_path / "ci" / "empty.yml", content)
    root = write(tmp_path / ".gitlab-ci.yml", "include: ci/empty.yml\n")
    with pytest.raises(ValueError, match="Included file 'ci/empty.yml' is empty"):
        load_and_resolve(root)


def test_included_file_that_is_not_a_mapping_fails(tmp_path):
    write(tmp_path / "ci" / "list.yml", "- a\n- b\n")
    root = write(tmp_path / ".gitlab-ci.yml", "include: ci/list.yml\n")
    with pytest.raises(ValueError, match="'ci/list.yml' must be a mapping of keywords, not a list"):
        load_and_resolve(root)


def test_included_file_without_a_yaml_extension_fails(tmp_path):
    write(tmp_path / "ci" / "jobs.txt", "job:\n  script: [echo]\n")
    root = write(tmp_path / ".gitlab-ci.yml", "include: ci/jobs.txt\n")
    with pytest.raises(ValueError, match="'ci/jobs.txt' does not have a YAML extension"):
        load_and_resolve(root)


def test_include_cycle_fails(tmp_path):
    write(tmp_path / "ci" / "a.yml", "include: ci/b.yml\n")
    write(tmp_path / "ci" / "b.yml", "include: ci/a.yml\n")
    root = write(tmp_path / ".gitlab-ci.yml", "include: ci/a.yml\n")
    with pytest.raises(ValueError, match="Include cycle: ci/a.yml -> ci/b.yml -> ci/a.yml"):
        load_and_resolve(root)


def test_root_file_including_itself_through_a_wildcard_fails(tmp_path):
    # `*.yml` matches the root .gitlab-ci.yml too, as in GitLab
    root = write(tmp_path / ".gitlab-ci.yml", "include: '*.yml'\njob:\n  script: [echo]\n")
    with pytest.raises(ValueError, match=r"Include cycle: \.gitlab-ci\.yml -> \.gitlab-ci\.yml"):
        load_and_resolve(root)


def test_same_file_included_twice_is_not_a_cycle(tmp_path):
    write(tmp_path / "ci" / "common.yml", ".common:\n  script: [echo]\n")
    write(tmp_path / "ci" / "a.yml", "include: ci/common.yml\n")
    root = write(tmp_path / ".gitlab-ci.yml", "include: [ci/common.yml, ci/a.yml]\njob:\n  script: [echo]\n")
    config, _ = load_and_resolve(root)
    assert ".common" in config


class TestExists:
    """rules:exists globs, with the syntax GitLab uses (File.fnmatch)."""

    @pytest.fixture
    def repo(self, tmp_path):
        for name in ("Dockerfile", "a1.txt", "sub/deep/x.txt", ".hidden.yml"):
            write(tmp_path / name, "")
        return str(tmp_path)

    @pytest.mark.parametrize("pattern, expected", [
        ("Dockerfile", True),
        ("**/Dockerfile", True),        # **/ also matches no directory
        ("**/x.txt", True),
        ("sub/**/x.txt", True),
        ("*/x.txt", False),             # * does not match a /
        ("a?.txt", True),
        ("a[0-9].txt", True),
        ("a[!0-9].txt", False),
        ("{a1,b1}.txt", True),
        ("s**/x.txt", False),           # **/ only as a whole segment: s**/ is s*/
        ("s**/deep/x.txt", True),
        ("{**/x.txt,nope}", True),
        ("sub/{**/x.txt,nope}", True),
        ("*.yml", True),                # dot files are matched
        ("nope*", False),
    ])
    def test_globs(self, repo, pattern, expected):
        assert include_rules_match([{"exists": [pattern]}], {}, repo) is expected

    def test_defined_variables_are_expanded(self, repo):
        assert include_rules_match([{"exists": ["$NAME"]}], {"NAME": "Dockerfile"}, repo)

    def test_undefined_variables_are_kept_as_written(self, repo):
        # As in GitLab, unlike in include paths: a${U}1.txt is not a1.txt
        assert not include_rules_match([{"exists": ["a${U}1.txt"]}], {}, repo)

    def test_exists_paths(self, repo):
        assert include_rules_match([{"exists": {"paths": ["Dockerfile"]}}], {}, repo)

    @pytest.mark.parametrize("pattern", [
        "/Dockerfile", "/sub/**/x.txt", "sub//deep/x.txt", "./Dockerfile",
        "sub/../Dockerfile", "sub/../a?.txt",
    ])
    def test_paths_are_taken_as_written(self, repo, pattern):
        # GitLab neither strips a leading slash nor normalises the path here
        assert not include_rules_match([{"exists": [pattern]}], {}, repo)

    @pytest.mark.parametrize("exists", [{}, [], {"paths": []}, {"paths": None}])
    def test_empty_exists_matches_nothing(self, repo, exists):
        assert not include_rules_match([{"exists": exists}], {}, repo)

    @pytest.mark.parametrize("exists", [
        {"project": "group/other", "paths": ["nope"]},
        {"project": "group/other", "paths": ["nope"], "ref": "main"},
        {"regexp": "nope.*"},
    ])
    def test_exists_that_cannot_be_checked_is_taken_as_matching(self, repo, caplog, exists):
        assert include_rules_match([{"exists": exists}], {}, repo)
        assert "taken as matching" in caplog.text

    @pytest.mark.parametrize("pattern", [".git/HEAD", "sub/.git/HEAD", ".git/*"])
    def test_git_directory_is_not_in_the_repository(self, repo, pattern):
        # As in GitLab, whose repository has no .git
        write(Path(repo) / ".git" / "HEAD", "")
        write(Path(repo) / "sub" / ".git" / "HEAD", "")
        assert not include_rules_match([{"exists": [pattern]}], {}, repo)

    def test_git_directory_is_skipped(self, repo):
        write(Path(repo) / ".git" / "config.yml", "")
        assert not include_rules_match([{"exists": ["**/config.yml"]}], {}, repo)

    def test_paths_outside_the_repository_do_not_match(self, tmp_path):
        write(tmp_path / "outside.yml", "")
        repo = tmp_path / "repo"
        repo.mkdir()
        assert not include_rules_match([{"exists": ["../outside.yml"]}], {}, str(repo))


class TestRulesConditions:
    def test_if_null_is_no_condition(self, tmp_path):
        assert include_rules_match([{"if": None}], {}, str(tmp_path))

    @pytest.mark.parametrize("condition, variables, included", [
        ("$CI_COMMIT_TAG =~ /^v/", {"CI_COMMIT_TAG": "v1"}, True),
        ("$DEPLOY_ENV != null", {}, False),
        ("$BRANCH =~ /^release/i", {"BRANCH": "Release-1"}, True),
        ('$QUOTED == \'say "hi"\'', {"QUOTED": 'say "hi"'}, True),
    ])
    def test_if_is_evaluated(self, tmp_path, condition, variables, included):
        write(tmp_path / "ci" / "jobs.yml", "inc_job:\n  script: [echo]\n")
        root = write(tmp_path / ".gitlab-ci.yml",
                     f"include:\n  - local: ci/jobs.yml\n    rules:\n      - if: {json.dumps(condition)}\n"
                     "job:\n  script: [echo]\n")
        config, _ = load_and_resolve(root, variables=variables)
        assert ("inc_job" in config) is included

    @pytest.mark.parametrize("condition", ["$X ==", "$X =~ /(/", "$X and $Y"])
    def test_invalid_if_fails(self, tmp_path, condition):
        # As in GitLab: include:rule if invalid expression syntax
        root = write(tmp_path / ".gitlab-ci.yml",
                     f"include:\n  - local: ci/missing.yml\n    rules:\n      - if: '{condition}'\n")
        with pytest.raises(ValueError, match=r"Include .*rules: invalid expression"):
            load_and_resolve(root, variables={"X": "1"})

    def test_if_that_cannot_be_evaluated_is_a_warning(self, tmp_path, caplog):
        # Valid in GitLab, but Python has no ungreedy flag: taken as not
        # matching, as for job rules, instead of stopping the load
        root = write(tmp_path / ".gitlab-ci.yml",
                     "include:\n  - local: ci/missing.yml\n    rules:\n      - if: '$X =~ /a+/U'\n"
                     "job:\n  script: [echo]\n")
        config, _ = load_and_resolve(root, variables={"X": "aa"})
        assert set(config) == {"job"}
        assert "Cannot evaluate an include rule" in caplog.text

    @pytest.mark.parametrize("rules, error", [
        # GitLab: include:rule if invalid expression syntax
        ("[{if: 5}]", "if must be an expression, not 5"),
        ("[{if: [a]}]", "if must be an expression, not \\['a'\\]"),
        # Also after a rule that matches
        ("[{if: '$CI'}, {if: 5}]", "if must be an expression, not 5"),
        ("[{when: never}, {if: 5}]", "if must be an expression, not 5"),
        # The syntax of every if is checked too, without evaluating it
        ("[{if: '$CI'}, {if: '$A =='}]", "invalid expression '\\$A =='"),
        ("[{when: never}, {if: '$A =~ /a(/'}]", "invalid expression '\\$A =~ /a\\(/'"),
        # Nested lists of rules are flattened and checked, as for job rules
        ("[[{if: '$A =='}]]", "invalid expression '\\$A =='"),
        # GitLab: include:rule config should be a hash
        ("[foo]", "a rule must be a mapping, not 'foo'"),
        # GitLab: include:rule when unknown value: on_success
        ("[{when: on_success}]", "when must be always or never, not 'on_success'"),
        ("[{when: manual}]", "when must be always or never, not 'manual'"),
        # GitLab: include:rule when unknown value: false (also '' and 0)
        ("[{when: false}]", "when must be always or never, not False"),
        ("[{when: ''}]", "when must be always or never, not ''"),
        ("[{when: 0}]", "when must be always or never, not 0"),
        # GitLab: include:rules config can't be blank
        ("[]", "must not be an empty list"),
        # GitLab: include:include rules should be an array of hashes
        ("[[]]", "must contain at least one rule"),
        # GitLab: include:rules config should be an array
        ("{if: '$CI'}", "must be a list of rules"),
        # GitLab: include:rule config contains unknown keys: foo
        ("[{if: '$CI', foo: 1}]", "unknown keys in a rule: foo"),
        # GitLab: include:rule:exists config contains unknown keys: foo
        ("[{exists: {paths: [a], foo: 1}}]", "unknown keys in exists: foo"),
        # GitLab: include:rule:exists config must use exactly one of these keys: paths, regexp
        ("[{exists: {project: g/p}}]", "exists must have either paths or regexp"),
        ("[{exists: {paths: [a], regexp: a}}]", "exists must have either paths or regexp"),
        ("[{exists: {ref: main}}]", "exists must have either paths or regexp"),
    ])
    @pytest.mark.parametrize("variables", [{"CI": "true"}, None], ids=["simulate", "validate"])
    def test_invalid_rules_fail(self, tmp_path, rules, error, variables):
        # Every rule is checked, even when the rules cannot be evaluated (no
        # variables, as in validate) or an earlier rule already matched
        write(tmp_path / "ci" / "jobs.yml", "job:\n  script: [echo]\n")
        root = write(tmp_path / ".gitlab-ci.yml",
                     f"include:\n  - local: ci/jobs.yml\n    rules: {rules}\n")
        with pytest.raises(ValueError, match=r"Include .*rules: " + error):
            load_and_resolve(root, variables=variables)

    @pytest.mark.parametrize("include", ["project: group/project\n    file: ci/jobs.yml",
                                         "remote: https://example.com/jobs.yml",
                                         "template: Jobs/Build.gitlab-ci.yml"])
    @pytest.mark.parametrize("rules, error", [
        ("[{when: always}, {if: '$A =='}]", "invalid expression '\\$A =='"),
        ("[foo]", "a rule must be a mapping, not 'foo'"),
    ])
    def test_rules_of_non_local_includes_are_checked(self, tmp_path, include, rules, error):
        # GitLab checks them too, although cimulator does not load the file
        root = write(tmp_path / ".gitlab-ci.yml",
                     f"include:\n  - {include}\n    rules: {rules}\njob:\n  script: [echo]\n")
        with pytest.raises(ValueError, match=r"Include .*rules: " + error):
            load_and_resolve(root, variables={})

    @pytest.mark.parametrize("rules", [
        "[{if: '$CI', exists: [a], changes: [b], when: always}]", "[{when: never}]", "[{if: null}]", "[[{if: '$CI'}, []]]",
        "[{exists: {}}]", "[{exists: {project: g/p, paths: [a], ref: main}}]",
        "[[{if: '$CI'}], [[{when: never}]]]",
    ])
    def test_valid_rules(self, tmp_path, rules):
        write(tmp_path / "ci" / "jobs.yml", "job:\n  script: [echo]\n")
        root = write(tmp_path / ".gitlab-ci.yml",
                     f"include:\n  - local: ci/jobs.yml\n    rules: {rules}\nother:\n  script: [echo]\n")
        load_and_resolve(root, variables={"CI": "true"})

    def test_without_variables_rules_without_if_are_evaluated(self, tmp_path):
        write(tmp_path / "ci" / "never.yml", "never_job:\n  script: [echo]\n")
        write(tmp_path / "ci" / "exists.yml", "exists_job:\n  script: [echo]\n")
        root = write(tmp_path / ".gitlab-ci.yml", """
include:
  - local: ci/never.yml
    rules:
      - when: never
  - local: ci/exists.yml
    rules:
      - exists: [Makefile]
job:
  script: [echo]
""")
        config, _ = load_and_resolve(root)
        assert set(config) == {"job"}

    def test_without_variables_an_if_without_variables_is_evaluated(self, tmp_path):
        # Variables are not expanded in quoted strings: "$A" is always "$A",
        # as checked against GitLab's pipeline dry run
        write(tmp_path / "ci" / "false.yml", "false_job:\n  script: [echo]\n")
        write(tmp_path / "ci" / "quoted.yml", "quoted_job:\n  script: [echo]\n")
        write(tmp_path / "ci" / "true.yml", "true_job:\n  script: [echo]\n")
        root = write(tmp_path / ".gitlab-ci.yml", """
include:
  - local: ci/false.yml
    rules:
      - if: '"" != ""'
  - local: ci/quoted.yml
    rules:
      - if: '"$CI_COMMIT_BRANCH" == "main"'
  - local: ci/true.yml
    rules:
      - if: '"a" == "a" && null == null'
job:
  script: [echo]
""")
        config, _ = load_and_resolve(root)
        assert set(config) == {"job", "true_job"}

    def test_without_variables_an_if_without_variables_uses_inputs(self, tmp_path):
        # The usual way to include a file only when an input is set
        write(tmp_path / "ci" / "release.yml", "release_job:\n  script: [echo]\n")
        root = write(tmp_path / ".gitlab-ci.yml", """spec:
  inputs:
    version:
      default: ""
---
include:
  - local: ci/release.yml
    rules:
      - if: '"$[[ inputs.version ]]" != ""'
job:
  script: [echo]
""")
        config, _ = load_and_resolve(root)
        assert "release_job" not in config
        config, _ = load_and_resolve(root, inputs={"version": "1.0"})
        assert "release_job" in config

    def test_without_variables_an_if_with_a_variable_is_not_evaluated(self, tmp_path):
        # The file is loaded, as it may be included
        write(tmp_path / "ci" / "jobs.yml", "other_job:\n  script: [echo]\n")
        root = write(tmp_path / ".gitlab-ci.yml", """
include:
  - local: ci/jobs.yml
    rules:
      - if: '"" != "" || $RELEASE'
job:
  script: [echo]
""")
        config, _ = load_and_resolve(root)
        assert "other_job" in config


def test_empty_path_segment_is_a_missing_file(tmp_path):
    # GitLab does not collapse ci//a.yml into ci/a.yml
    write(tmp_path / "ci" / "a.yml", "job:\n  script: [echo]\n")
    root = write(tmp_path / ".gitlab-ci.yml", "include: ci/$UNDEFINED/a.yml\n")
    with pytest.raises(ValueError, match="'ci//a.yml' does not exist"):
        load_and_resolve(root, variables={})


@pytest.mark.parametrize("content", ["[]\n", "false\n", "0\n", "''\n", "[1]\n"])
def test_included_file_whose_value_is_not_a_mapping_fails(tmp_path, content):
    write(tmp_path / "ci" / "x.yml", content)
    root = write(tmp_path / ".gitlab-ci.yml", "include: ci/x.yml\n")
    with pytest.raises(ValueError, match="'ci/x.yml' must be a mapping of keywords"):
        load_and_resolve(root)


def test_root_file_that_is_not_a_mapping_fails(tmp_path):
    root = write(tmp_path / ".gitlab-ci.yml", "[]\n")
    with pytest.raises(ValueError, match="'.gitlab-ci.yml' must be a mapping of keywords, not a list"):
        load_and_resolve(root)


def test_dot_segment_is_a_missing_file(tmp_path):
    # GitLab rejects ./ci/a.yml: Local file `./ci/a.yml` does not exist!
    write(tmp_path / "ci" / "a.yml", "job:\n  script: [echo]\n")
    root = write(tmp_path / ".gitlab-ci.yml", "include: ./ci/a.yml\n")
    with pytest.raises(ValueError, match="'./ci/a.yml' does not exist"):
        load_and_resolve(root)


def test_dot_segment_in_a_wildcard_matches_nothing(tmp_path, caplog):
    # GitLab accepts ./ci/*.yml, which matches no file
    write(tmp_path / "ci" / "a.yml", "job:\n  script: [echo]\n")
    root = write(tmp_path / ".gitlab-ci.yml", "include: './ci/*.yml'\nother:\n  script: [echo]\n")
    config, _ = load_and_resolve(root)
    assert set(config) == {"other"}
    assert "does not match any file" in caplog.text



def test_dot_dot_segment_is_a_missing_file(tmp_path):
    # GitLab: Local file `ci/../ci/a.yml` does not exist!
    write(tmp_path / "ci" / "a.yml", "job:\n  script: [echo]\n")
    root = write(tmp_path / ".gitlab-ci.yml", "include: ci/../ci/a.yml\n")
    with pytest.raises(ValueError, match="'ci/../ci/a.yml' does not exist"):
        load_and_resolve(root)


def test_dot_dot_segment_in_a_wildcard_matches_nothing(tmp_path, caplog):
    # GitLab accepts ci/../ci/*.yml, which matches no file
    write(tmp_path / "ci" / "a.yml", "job:\n  script: [echo]\n")
    root = write(tmp_path / ".gitlab-ci.yml", "include: 'ci/../ci/*.yml'\nother:\n  script: [echo]\n")
    config, _ = load_and_resolve(root)
    assert set(config) == {"other"}
    assert "does not match any file" in caplog.text


def test_when_null_is_always(tmp_path):
    # As in GitLab, like if: null
    write(tmp_path / "ci" / "a.yml", "job:\n  script: [echo]\n")
    root = write(tmp_path / ".gitlab-ci.yml",
                 "include:\n  - local: ci/a.yml\n    rules:\n      - when: null\n")
    for variables in ({}, None):
        config, _ = load_and_resolve(root, variables=variables)
        assert set(config) == {"job"}


def test_wildcard_skips_the_git_directory(tmp_path):
    write(tmp_path / "ci" / "x.yml", "job:\n  script: [echo]\n")
    write(tmp_path / ".git" / "hooks" / "x.yml", "not a job: [\n")
    root = write(tmp_path / ".gitlab-ci.yml", "include: '**/x.yml'\n")
    config, _ = load_and_resolve(root)
    assert set(config) == {"job"}


@pytest.mark.parametrize("git", ["directory", "file"])
def test_submodules_are_not_part_of_the_repository(tmp_path, caplog, git):
    # GitLab sees neither the files of a submodule nor its .git, which is a
    # file in a submodule or a worktree. The root may have one too.
    write(tmp_path / "ci" / "x.yml", "job:\n  script: [echo]\n")
    if git == "directory":
        write(tmp_path / "sub" / ".git" / "HEAD", "")
    else:
        write(tmp_path / "sub" / ".git", "gitdir: elsewhere\n")
    write(tmp_path / ".git", "gitdir: elsewhere\n")
    write(tmp_path / "sub" / "ci" / "x.yml", "not a job: [\n")
    root = write(tmp_path / ".gitlab-ci.yml", "include: '**/x.yml'\n")
    config, _ = load_and_resolve(root)
    assert set(config) == {"job"}

    root = write(tmp_path / ".gitlab-ci.yml", "include: 'sub/ci/*.yml'\n")
    config, _ = load_and_resolve(root)
    assert config == {}

    root = write(tmp_path / ".gitlab-ci.yml", "include: sub/ci/x.yml\n")
    with pytest.raises(ValueError, match="'sub/ci/x.yml' does not exist"):
        load_and_resolve(root)

    for pattern in [".gi?", "sub", "sub/ci/x.yml", "sub/**/x.yml", "sub/ci/*.yml", "**/.git", "sub/.git"]:
        assert not include_rules_match([{"exists": [pattern]}], {}, str(tmp_path)), pattern
    assert include_rules_match([{"exists": ["ci/x.yml"]}], {}, str(tmp_path))


def test_spec_header_without_configuration_comes_before_inputs(tmp_path):
    write(tmp_path / "ci" / "x.yml", "spec:\n  inputs:\n    a:\n---\n")
    root = write(tmp_path / ".gitlab-ci.yml", "include: ci/x.yml\njob:\n  script: [echo]\n")
    with pytest.raises(ValueError, match="'ci/x.yml' has a spec header but no configuration after it"):
        load_and_resolve(root)


def test_root_file_with_only_a_spec_header_fails(tmp_path):
    # As in GitLab; an empty root file is an empty pipeline
    root = write(tmp_path / ".gitlab-ci.yml", "spec:\n  inputs:\n    a:\n      default: x\n---\n")
    with pytest.raises(ValueError, match="'.gitlab-ci.yml' has a spec header but no configuration after it"):
        load_and_resolve(root)
    write(tmp_path / ".gitlab-ci.yml", "# nothing yet\n")
    config, _ = load_and_resolve(root)
    assert config == {}


def test_plain_path_in_the_git_directory_is_a_missing_file(tmp_path):
    write(tmp_path / ".git" / "a.yml", "job:\n  script: [echo]\n")
    root = write(tmp_path / ".gitlab-ci.yml", "include: .git/a.yml\n")
    with pytest.raises(ValueError, match="'.git/a.yml' does not exist"):
        load_and_resolve(root)


@pytest.mark.parametrize("content", [
    "spec:\n  inputs:\n    a:\n      default: x\n---\n",
    "spec:\n  inputs:\n    a:\n      default: x\n---\n# only a comment\n",
])
def test_spec_header_without_configuration_fails(tmp_path, content):
    # GitLab rejects it too (it reads spec as a job without script)
    write(tmp_path / "ci" / "x.yml", content)
    root = write(tmp_path / ".gitlab-ci.yml", "include: ci/x.yml\njob:\n  script: [echo]\n")
    with pytest.raises(ValueError, match="'ci/x.yml' has a spec header but no configuration after it"):
        load_and_resolve(root)
