import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

import test_patchproof as original
from patchproof import CaseOutcome, ExecutionResult, FailureExpectation, aggregate_attempts, classify, verify_patch
from patchproof.cli import load_expectations
from patchproof.proposals import AnthropicProposalAdapter, NoRedirect, send_anthropic, validate_proposal, write_proposal
from patchproof.runners import DockerRunner, parse_junit
from patchproof.service import validate_dependencies


def outcome(status, node='test_regression::test_add'):
    message = 'AssertionError: BUG_ADD' if status == 'failed' else ''
    return ExecutionResult(status, 1, [message] if message else [], node_ids=[node],
                           cases=[CaseOutcome(node, status, message, 'AssertionError' if message else None)])


def attempt(base, patched, verdict):
    return {'results': {'base': base, 'patched': patched}, 'verdict': verdict, 'reason': verdict}


class RepetitionTests(unittest.TestCase):
    def test_stable_repetitions(self):
        runs = [attempt(outcome('failed'), outcome('passed'), 'supported') for _ in range(3)]
        self.assertEqual(aggregate_attempts(runs)[0], 'supported')

    def test_flaky_case(self):
        runs = [attempt(outcome('failed'), outcome('passed'), 'supported'),
                attempt(outcome('passed'), outcome('passed'), 'not_reproduced')]
        self.assertEqual(aggregate_attempts(runs)[0], 'flaky')

    def test_infrastructure_drift_is_inconsistent(self):
        runs = [attempt(outcome('failed'), outcome('passed'), 'supported'),
                attempt(ExecutionResult('inconclusive'), outcome('passed'), 'inconclusive')]
        self.assertEqual(aggregate_attempts(runs)[0], 'inconsistent')

    def test_case_collection_drift_is_inconsistent(self):
        runs = [attempt(outcome('failed'), outcome('passed'), 'supported'),
                attempt(outcome('failed', 'other'), outcome('passed', 'other'), 'supported')]
        self.assertEqual(aggregate_attempts(runs)[0], 'inconsistent')

    def test_exact_case_exception_and_message(self):
        expectation = (FailureExpectation('test_regression::test_add', 'BUG_ADD', 'AssertionError'),)
        self.assertEqual(classify(outcome('failed'), outcome('passed'), '', expectations=expectation)[0], 'supported')
        wrong = (FailureExpectation('test_regression::test_add', 'BUG_ADD', 'ValueError'),)
        self.assertEqual(classify(outcome('failed'), outcome('passed'), '', expectations=wrong)[0], 'inconclusive')

    def test_unexpected_failing_case_is_rejected(self):
        expected = (FailureExpectation('test_regression::different', 'BUG_ADD'),)
        self.assertEqual(classify(outcome('failed'), outcome('passed'), '', expectations=expected)[0], 'inconclusive')

    def test_dependency_mismatch(self):
        with self.assertRaises(ValueError):
            validate_dependencies({'schema_version': 1, 'packages': {'pytest': '9.1.1'}}, {'packages': []})

    def test_dependency_manifest_accepts_exact_match(self):
        validate_dependencies({'schema_version': 1, 'python_version': '3.13.16', 'packages': {'pytest': '9.1.1'}},
                              {'python_version': '3.13.16', 'packages': [{'name': 'pytest', 'version': '9.1.1'}]})

    def test_junit_symlink_is_never_followed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            secret = root / 'secret'
            secret.write_text('host secret fixture')
            report = root / 'junit.xml'
            report.symlink_to(secret)
            result = parse_junit(report, 0)
            self.assertEqual(result.status, 'inconclusive')
            self.assertEqual(result.junit_xml, '')


class ExtendedIntegrationTests(unittest.TestCase):
    setUp = original.IntegrationTests.setUp
    git = original.IntegrationTests.git
    request = original.IntegrationTests.request

    def test_repeated_real_runs_keep_xml_artifacts(self):
        request = self.request(repeat_count=3)
        result = verify_patch(request, runner=self.runner)
        self.assertEqual(result['verdict'], 'supported')
        self.assertEqual(len(result['attempts']), 3)
        for run in result['attempts']:
            for execution in run['executions'].values():
                ref = execution['artifacts']['junit.xml']
                data = (request.output / ref['path']).read_bytes()
                self.assertTrue(data.startswith(b'<?xml'))
                self.assertEqual(hashlib.sha256(data).hexdigest(), ref['sha256'])
        self.assertTrue((request.output / 'environment.json').is_file())

    def test_real_case_contract(self):
        result = verify_patch(self.request(expected_failure='', expectations=(
            FailureExpectation('test_regression::test_add', 'BUG_ADD', 'AssertionError'),)), runner=self.runner)
        self.assertEqual(result['verdict'], 'supported')

    def test_failure_contract_json(self):
        expected = self.root / 'expectations.json'
        expected.write_text(json.dumps({'schema_version': 1, 'cases': [
            {'node_id': 'test_regression::test_add', 'message_contains': 'BUG_ADD', 'exception_type': 'AssertionError'}]}))
        self.assertEqual(load_expectations(expected)[0].exception_type, 'AssertionError')

    def test_proposal_cannot_be_run_without_review_rename(self):
        proposed = self.root / 'test.py.proposed'
        proposed.write_text(self.test.read_text())
        with self.assertRaisesRegex(ValueError, 'reviewed'):
            verify_patch(self.request(test=proposed), runner=self.runner)

    def test_dependency_failure_prevents_test_execution(self):
        manifest = self.root / 'dependencies.json'
        manifest.write_text(json.dumps({'schema_version': 1, 'packages': {'pytest': '0.0.0'}}))
        with patch.object(self.runner, 'run') as run, self.assertRaisesRegex(ValueError, 'mismatch'):
            verify_patch(self.request(dependency_manifest=manifest), runner=self.runner)
        run.assert_not_called()

    def test_repeat_limit(self):
        with self.assertRaises(ValueError):
            verify_patch(self.request(repeat_count=21), runner=self.runner)


PROPOSAL = {'test_code': 'def test_add():\n    assert 1 == 2, "BUG_ADD"\n',
            'expectations': [{'node_id': 'test_regression::test_add', 'message_contains': 'BUG_ADD', 'exception_type': 'AssertionError'}],
            'explanation': 'Check the reported addition result.', 'assumptions': ['Illustrative fixture only.']}


class ProposalTests(unittest.TestCase):
    def response(self, payload, key, timeout):
        self.assertEqual(payload['tool_choice']['name'], 'propose_regression_test')
        self.assertEqual(key, 'fixture-not-a-real-key')
        self.assertNotIn('tool_result', json.dumps(payload))
        return {'stop_reason': 'tool_use', 'content': [{'type': 'tool_use', 'name': 'propose_regression_test', 'input': PROPOSAL}],
                'usage': {'input_tokens': 10, 'output_tokens': 20}}

    def test_explicit_remote_opt_in(self):
        with self.assertRaisesRegex(ValueError, 'allow_remote'):
            AnthropicProposalAdapter('fixture-model').propose({})

    def test_schema_and_syntax_validation(self):
        for value in ({**PROPOSAL, 'execute': True}, {**PROPOSAL, 'test_code': 'this is invalid syntax +'},
                      {**PROPOSAL, 'expectations': []}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_proposal(value)

    def test_proposal_saved_as_untrusted_non_python_file(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'fixture-not-a-real-key'}):
            root = Path(folder)
            issue, diff = root / 'issue.txt', root / 'fix.diff'
            issue.write_text('Addition bug'); diff.write_text('illustrative diff')
            result = write_proposal(issue=issue, patch=diff, sources=(), output=root / 'proposal',
                adapter=AnthropicProposalAdapter('fixture-model', True, transport=self.response))
            self.assertFalse(result['trusted'])
            self.assertEqual(result['execution'], 'not performed')
            self.assertEqual(list((root / 'proposal').glob('*.py')), [])
            self.assertTrue((root / 'proposal' / 'test_regression.py.proposed').exists())
            self.assertNotIn('fixture-not-a-real-key', (root / 'proposal' / 'proposal.json').read_text())

    def test_truncated_provider_output_rejected(self):
        with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'fixture-not-a-real-key'}), self.assertRaises(ValueError):
            AnthropicProposalAdapter('fixture-model', True, transport=lambda *args: {'stop_reason': 'max_tokens'}).propose({})

    def test_input_and_token_budgets(self):
        with self.assertRaises(ValueError):
            AnthropicProposalAdapter('fixture-model', True, max_tokens=9000).propose({})
        with self.assertRaises(ValueError):
            AnthropicProposalAdapter('fixture-model', True).propose({'source': 'x' * 65000})

    def test_same_and_cross_origin_redirects_are_refused(self):
        request = urllib.request.Request('https://api.anthropic.com/v1/messages',
                                         headers={'x-api-key': 'fixture-only-key'})
        for destination in ('https://api.anthropic.com/redirected', 'https://unrelated.example/collect'):
            with self.subTest(destination=destination), self.assertRaises(ValueError) as caught:
                NoRedirect().redirect_request(request, None, 307, 'redirect', {}, destination)
            self.assertNotIn('fixture-only-key', str(caught.exception))
        opener = urllib.request.build_opener(NoRedirect)
        self.assertTrue(any(isinstance(handler, NoRedirect) for handler in opener.handlers))

    def test_provider_error_body_is_not_in_exception(self):
        import io
        errors = [urllib.error.HTTPError('https://api.anthropic.com/v1/messages', 403,
                    'fixture-secret-message', {}, io.BytesIO(b'fixture-secret-body')),
                  urllib.error.URLError('fixture-secret-message')]
        for error in errors:
            with patch('patchproof.proposals.urllib.request.build_opener') as factory:
                factory.return_value.open.side_effect = error
                with self.assertRaises(ValueError) as caught:
                    send_anthropic({}, 'fixture-only-key', 3)
            for secret in ('fixture-secret-body', 'fixture-secret-message', 'fixture-only-key'):
                self.assertNotIn(secret, str(caught.exception))


@unittest.skipUnless(os.environ.get('PATCHPROOF_DOCKER_IMAGE'), 'Set PATCHPROOF_DOCKER_IMAGE to run live container fixtures')
class DockerIntegrationTests(unittest.TestCase):
    setUp = original.IntegrationTests.setUp
    git = original.IntegrationTests.git
    request = original.IntegrationTests.request

    def docker_runner(self):
        return DockerRunner(os.environ['PATCHPROOF_DOCKER_IMAGE'])

    def test_live_fail_before_pass_after_and_manifest(self):
        result = verify_patch(self.request(repeat_count=2), runner=self.docker_runner())
        self.assertEqual(result['verdict'], 'supported')
        self.assertTrue(result['environment']['image_id'].startswith('sha256:'))
        self.assertTrue(any(p['name'] == 'pytest' for p in result['environment']['packages']))

    def test_network_filesystem_identity_and_environment_boundaries(self):
        self.test.write_text('''import os, socket
from pathlib import Path
import pytest

def test_boundaries():
    assert os.geteuid() == 65534
    assert "PATCHPROOF_TEST_SECRET" not in os.environ
    with pytest.raises(OSError):
        Path("/work/should_not_be_writable").write_text("blocked")
    with pytest.raises(OSError):
        socket.create_connection(("1.1.1.1", 443), timeout=1)
''')
        with patch.dict(os.environ, {'PATCHPROOF_TEST_SECRET': 'fixture-only'}):
            result = verify_patch(self.request(), runner=self.docker_runner())
        self.assertEqual(result['executions']['base']['status'], 'passed')
        self.assertEqual(result['executions']['patched']['status'], 'passed')

    def test_timeout_container_removed(self):
        (self.repo / 'test_wait.py').write_text('import time\ndef test_wait():\n    time.sleep(30)\n')
        result = self.docker_runner().run(self.repo, ('test_wait.py',), timeout=2, regression=False)
        self.assertEqual(result.status, 'inconclusive')
        self.assertEqual(result.reason, 'Execution timed out')
        name = result.command[result.command.index('--name') + 1]
        check = subprocess.run(['docker', 'inspect', name], capture_output=True)
        self.assertNotEqual(check.returncode, 0)


if __name__ == '__main__':
    unittest.main()
