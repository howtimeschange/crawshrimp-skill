import copy
import json
from pathlib import Path
import tempfile
import unittest

from scripts.jev_operator import (
    Handoff, JevOperator, ChatDecisionClient, decode_decision, endpoint, questions_for,
    read_config, validate_answer, within_target,
)


def answer(choice, choices, confidence=1):
    return {'choice': choice, 'confidence': confidence,
            'probabilities': {key: float(key == choice) for key in choices}}


def page(**changes):
    return {'snapshot_id': 'doc:1', 'url': 'https://example.test/report', 'title': 'Report',
            'ready': 'complete', 'text': 'Next', 'progress': 'rows1', 'data': None,
            'verified': False, 'blocked': False, 'unavailable': False, 'scope_found': True,
            'elements': [{'ref': 'e1', 'name': 'Next', 'role': 'button', 'value': '',
                          'context': 'Page 1', 'operations': ['CLICK']}], **changes}


class Client:
    def __init__(self, operation='CLICK'):
        self.operation = operation
        self.calls = []

    def post(self, state, questions):
        self.calls.append((state, questions))
        answers = {'operation': answer(self.operation, questions['operation']['criteria'])}
        if self.operation == 'CLICK':
            answers['click_target'] = answer('e1', questions['click_target']['criteria'])
        return {'model': 'fixture', 'answers': answers}


class UncertainClient(Client):
    def post(self, state, questions):
        result = super().post(state, questions)
        result['answers']['operation']['confidence'] = .3
        return result


class Session:
    def __init__(self, pages, *, uncertain=False):
        self.pages = list(pages)
        self.calls = 0
        self.actions = []
        self.commands = []
        self.uncertain = uncertain

    async def evaluate(self, expression):
        self.calls += 1
        if expression.startswith('window.__crawshrimpJev'):
            self.actions.append(expression)
            if self.uncertain:
                raise ConnectionError('Disconnected after dispatch')
            return {'ok': True, 'status': 'executed', 'executed': True}
        return copy.deepcopy(self.pages.pop(0) if len(self.pages) > 1 else self.pages[0])

    async def call(self, method, params):
        self.calls += 1
        self.commands.append((method, params))
        return {}


class PolicyTest(unittest.TestCase):
    def test_fanout_uses_one_payload_and_compatible_targets(self):
        snapshot = page()
        snapshot['elements'].append({'ref': 'e2', 'name': 'Search', 'role': 'input',
            'value': '', 'context': 'Search books', 'operations': ['TYPE_TEXT']})
        qs, targets = questions_for(snapshot, 'Find books', {'Search': 'poetry'})
        self.assertEqual(set(qs), {'operation', 'click_target', 'type_text_target'})
        self.assertEqual(set(targets['CLICK']), {'e1'})
        self.assertEqual(targets['TYPE_TEXT']['e2']['fill_value'], 'poetry')
        without_values, _ = questions_for(snapshot, 'Find books')
        self.assertNotIn('TYPE_TEXT', without_values['operation']['criteria'])

    def test_selected_head_only_is_validated(self):
        qs, targets = questions_for(page(), 'Next')
        raw = {'answers': {'operation': answer('CLICK', qs['operation']['criteria']),
                          'click_target': answer('e1', targets['CLICK']),
                          'type_text_target': {'malformed': True}}}
        self.assertEqual(decode_decision(raw, qs, targets)['ref'], 'e1')

    def test_invalid_distribution_or_target_is_refused(self):
        for invalid in [answer('other', {'a'}), {'choice': 'a', 'confidence': True, 'probabilities': {'a': 1}},
                        {'choice': 'a', 'confidence': 1, 'probabilities': {'a': float('nan')}},
                        {'choice': 'a', 'confidence': 1, 'probabilities': []}]:
            with self.subTest(invalid=invalid), self.assertRaises(Handoff):
                validate_answer(invalid, {'a'})

    def test_low_target_confidence_cannot_execute(self):
        qs, targets = questions_for(page(), 'Next')
        raw = {'answers': {'operation': answer('CLICK', qs['operation']['criteria']),
                          'click_target': answer('e1', targets['CLICK'], .3)}}
        with self.assertRaisesRegex(Handoff, 'target confidence'):
            decode_decision(raw, qs, targets)

    def test_malformed_answers_envelope_hands_off(self):
        qs, targets = questions_for(page(), 'Next')
        with self.assertRaisesRegex(Handoff, 'answers object'):
            decode_decision({'answers': None}, qs, targets)

    def test_oversized_head_requests_narrower_scope(self):
        snapshot = page()
        snapshot['elements'] = [{'ref': f'e{i}', 'name': 'Next', 'role': 'button',
            'value': '', 'context': '', 'operations': ['CLICK']} for i in range(256)]
        with self.assertRaisesRegex(Handoff, '255'):
            questions_for(snapshot, 'Next')

    def test_chat_fallback_selects_only_offered_ids(self):
        qs, _ = questions_for(page(), 'Next')
        client = ChatDecisionClient('fixture-key', 'https://chat.example/v1', 'fixture')
        client.request = lambda payload: {'choices': [{'message': {'content': '{"operation":"CLICK","target":"e1"}'}}]}
        result = client.post({}, qs)
        self.assertEqual(result['answers']['click_target']['choice'], 'e1')
        self.assertEqual(result['confidence_kind'], 'format_adapter_not_calibrated')

    def test_chat_fallback_cannot_turn_generated_code_into_a_target(self):
        qs, _ = questions_for(page(), 'Next')
        client = ChatDecisionClient('fixture-key', 'https://chat.example/v1', 'fixture')
        client.request = lambda payload: {'choices': [{'message': {'content': '{"operation":"CLICK","target":"document.body.click()"}'}}]}
        with self.assertRaisesRegex(Handoff, 'offered IDs'):
            client.post({}, qs)

    def test_target_envelope_checks_origin_not_just_prefix(self):
        self.assertTrue(within_target('https://example.test/report/2', 'https://example.test/report'))
        self.assertFalse(within_target('https://example.test.evil/report', 'https://example.test'))
        self.assertFalse(within_target('http://example.test/report', 'https://example.test'))

    def test_endpoint_versions_and_existing_actions(self):
        self.assertEqual(endpoint('https://api.test/v1'), 'https://api.test/v1/systemone')
        self.assertEqual(endpoint('https://api.test'), 'https://api.test/v1/systemone')
        self.assertEqual(endpoint('https://gateway.test/api/alpha/decisions'), 'https://gateway.test/api/alpha/decisions')

    def test_config_does_not_import_unrelated_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'env'
            p.write_text('export TYPESAFE_API_KEY="test-key"\nexport OPENAI_API_KEY="other-key"\n')
            config = read_config(p)
        self.assertEqual(config['TYPESAFE_API_KEY'], 'test-key')
        self.assertNotIn('OPENAI_API_KEY', config)


class LoopTest(unittest.IsolatedAsyncioTestCase):
    def operator(self, session, client=None, **kwargs):
        return JevOperator(session, client or Client(), goal='Open next report',
            expected_url='https://example.test/report', scope='nav', verify_expression='goalComplete',
            settle_ms=10, max_seconds=2, **kwargs)

    async def test_independent_verification_completes_with_one_decision(self):
        s = Session([page(), page(verified=True, progress='rows2')])
        client = Client()
        result = await self.operator(s, client).run()
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['model_calls'], 1)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(len(s.actions), 1)

    async def test_already_complete_needs_no_model(self):
        s = Session([page(verified=True)])
        result = await self.operator(s).run()
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['model_calls'], 0)

    async def test_low_confidence_uses_bounded_optional_fallback(self):
        s = Session([page(), page(verified=True, progress='rows2')])
        fallback = Client()
        result = await self.operator(s, UncertainClient(), fallback_client=fallback).run()
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['fallback_calls'], 1)
        self.assertEqual(result['model_calls'], 2)
        self.assertEqual(len(s.actions), 1)

    async def test_low_confidence_without_fallback_never_executes(self):
        s = Session([page()])
        result = await self.operator(s, UncertainClient()).run()
        self.assertEqual(result['status'], 'handoff')
        self.assertFalse(s.actions)

    async def test_done_cannot_override_failed_code_proof(self):
        s = Session([page()])
        result = await self.operator(s, Client('DONE')).run()
        self.assertEqual(result['status'], 'handoff')
        self.assertIn('DONE was rejected', result['reason'])
        self.assertFalse(s.actions)

    async def test_unknown_input_is_not_replayed(self):
        s = Session([page()], uncertain=True)
        result = await self.operator(s).run()
        self.assertIn('BROWSER_ACTION_UNCERTAIN', result['reason'])
        self.assertEqual(len(s.actions), 1)
        self.assertFalse(s.commands)

    async def test_cached_content_is_polled_until_data_changes(self):
        s = Session([page(), page(), page(progress='rows2', verified=True)])
        operator = self.operator(s)
        operator.settle_ms = 200
        result = await operator.run()
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(len(s.actions), 1)
        self.assertEqual(len(result['observations']), 3)

    async def test_partial_document_data_is_not_given_to_model(self):
        s = Session([page(read_error='TypeError'), page(), page(verified=True)])
        client = Client()
        result = await self.operator(s, client).run()
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['model_calls'], 1)

    async def test_post_action_read_error_waits_for_result(self):
        s = Session([page(), page(read_error='TypeError', progress=None), page(verified=True)])
        operator = self.operator(s)
        operator.settle_ms = 250
        result = await operator.run()
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(len(s.actions), 1)

    async def test_captcha_never_reloads(self):
        s = Session([page(blocked=True)])
        result = await self.operator(s).run()
        self.assertIn('captcha', result['reason'])
        self.assertFalse(s.commands)
        self.assertFalse(s.actions)

    async def test_page_unavailable_refreshes_once_and_reads_back(self):
        s = Session([page(unavailable=True), page(verified=True)])
        result = await self.operator(s).run()
        self.assertEqual(result['status'], 'complete')
        self.assertEqual([x[0] for x in s.commands], ['Page.reload'])

    async def test_reload_to_home_restores_expected_target(self):
        s = Session([page(unavailable=True), page(url='https://example.test/'), page(verified=True)])
        result = await self.operator(s).run()
        self.assertEqual(result['status'], 'complete')
        self.assertEqual([x[0] for x in s.commands], ['Page.reload', 'Page.navigate'])

    async def test_other_origin_is_never_reloaded(self):
        s = Session([page(url='https://other.test/', unavailable=True)])
        result = await self.operator(s).run()
        self.assertEqual(result['status'], 'handoff')
        self.assertFalse(s.commands)
