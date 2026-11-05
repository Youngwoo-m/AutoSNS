"""Pure integration API helpers; routing/authentication belongs to web_server.

validate_settings_body(body) returns account_id, provider_id, connection_id,
expected_revision, payload. settings_response(items) returns the GET envelope.
Validation errors use content_store.StoreError('invalid').
"""
from common.operations.integration_store import PAYLOAD_FIELDS, validate_settings
from common.operations.content_store import StoreError

KEY_FIELDS = frozenset(('account_id', 'provider_id', 'connection_id', 'expected_revision'))


def validate_settings_body(body):
    if not isinstance(body, dict) or set(body) != KEY_FIELDS | PAYLOAD_FIELDS:
        raise StoreError('invalid')
    values = tuple(body[field] for field in ('account_id', 'provider_id', 'connection_id', 'expected_revision'))
    payload = validate_settings(*values, {field: body[field] for field in PAYLOAD_FIELDS})
    return (*values, payload)


def settings_response(items):
    return {'items': items}
