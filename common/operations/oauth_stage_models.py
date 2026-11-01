"""Private owned credential identities and strict, explicit storage codecs."""
from dataclasses import dataclass
import re
import uuid

from .credential_backend import CredentialError, validate_ref
from .oauth_models import CredentialRef


_LEGACY_FIELDS = ('namespace', 'account_id', 'platform', 'connection_id', 'generation', 'kind')
_OWNED_FIELDS = {'format', 'ref', 'workspace_id', 'root_binding', 'stage_id'}


def _invalid():
    raise CredentialError('credential_invalid_ref')


def _owner_identity(workspace_id, root_binding):
    if (type(workspace_id) is not str or not re.fullmatch(r'[0-9a-f]{32}', workspace_id)
            or uuid.UUID(hex=workspace_id).version != 4
            or type(root_binding) is not str or not re.fullmatch(r'[0-9a-f]{64}', root_binding)):
        _invalid()


class _Private:
    def __repr__(self):
        return type(self).__name__ + '(<private>)'

    def to_dict(self, *, public=True):
        if not public:
            raise CredentialError('credential_private_serialization_forbidden')
        return {}


@dataclass(frozen=True, repr=False)
class WorkspaceOwner(_Private):
    workspace_id: str
    root_binding: str
    format_version: int = 1

    def __post_init__(self):
        _owner_identity(self.workspace_id, self.root_binding)
        if type(self.format_version) is not int or self.format_version != 1:
            _invalid()


@dataclass(frozen=True, repr=False)
class OwnedCredentialRef(_Private):
    ref: CredentialRef
    workspace_id: str
    root_binding: str
    stage_id: str

    def __post_init__(self):
        validate_ref(self.ref)
        _owner_identity(self.workspace_id, self.root_binding)
        if type(self.stage_id) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', self.stage_id):
            _invalid()


StoredCredentialRef = CredentialRef | OwnedCredentialRef


def logical_ref(value: StoredCredentialRef) -> CredentialRef:
    """Return the logical legacy fields without changing the stored identity."""
    if type(value) is OwnedCredentialRef:
        value.__post_init__()
        return value.ref
    if type(value) is CredentialRef:
        validate_ref(value)
        return value
    _invalid()


def encode_stored_ref(value: StoredCredentialRef) -> dict:
    ref = logical_ref(value)
    legacy = {field: getattr(ref, field) for field in _LEGACY_FIELDS}
    if type(value) is CredentialRef:
        return legacy
    return dict(format='owned_v1', ref=legacy, workspace_id=value.workspace_id,
                root_binding=value.root_binding, stage_id=value.stage_id)


def _decode_legacy(value):
    if type(value) is not dict or set(value) != set(_LEGACY_FIELDS):
        _invalid()
    if (any(type(value[field]) is not str for field in _LEGACY_FIELDS if field != 'generation')
            or type(value['generation']) is not int):
        _invalid()
    # Validate before construction so malformed storage always uses sanitized errors.
    try:
        ref = CredentialRef(**value)
        validate_ref(ref)
    except Exception:
        raise CredentialError('credential_invalid_ref') from None
    return ref


def decode_stored_ref(value) -> StoredCredentialRef:
    if type(value) is not dict:
        _invalid()
    if 'format' not in value:
        return _decode_legacy(value)
    if set(value) != _OWNED_FIELDS or type(value['format']) is not str or value['format'] != 'owned_v1':
        _invalid()
    return OwnedCredentialRef(_decode_legacy(value['ref']), value['workspace_id'],
                              value['root_binding'], value['stage_id'])
