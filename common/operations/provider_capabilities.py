"""서버 소유 기능 목록. 연결이나 자격 증명을 조회하지 않는다."""
from dataclasses import asdict, dataclass
from types import MappingProxyType


@dataclass(frozen=True)
class ToolCapability:
    action_id: str
    provider_id: str
    platforms: tuple[str, ...]
    effect: str
    implementation_status: str
    runtime_kind: str
    cost_kind: str
    required_evidence: tuple[str, ...]

    def __post_init__(self):
        for name in ('action_id', 'provider_id'):
            if type(getattr(self, name)) is not str or not getattr(self, name):
                raise ValueError(name)
        for name in ('platforms', 'required_evidence'):
            value = getattr(self, name)
            if type(value) is not tuple or any(type(x) is not str or not x for x in value):
                raise ValueError(name)
        for name, options in (
            ('effect', ('read', 'local_write', 'external_write')),
            ('implementation_status', ('implemented', 'candidate')),
            ('runtime_kind', ('local', 'codex_assisted', 'unavailable')),
            ('cost_kind', ('no_additional_cost', 'credits', 'paid', 'unknown')),
        ):
            if type(getattr(self, name)) is not str or getattr(self, name) not in options:
                raise ValueError(name)


_LOCAL_ACTIONS = ('packaging.preview', 'research.preview', 'thumbnail.inspect',
                  'thumbnail.render', 'metrics.csv.preview', 'metrics.csv.import', 'schedule.inspect')
DEFAULT_CAPABILITIES = MappingProxyType({item.action_id: item for item in (
    *(ToolCapability('local.' + action, 'local', (),
                     'local_write' if action in ('thumbnail.render', 'metrics.csv.import') else 'read',
                     'implemented', 'local', 'no_additional_cost', ('builtin:local-toolkit:v1',))
      for action in _LOCAL_ACTIONS),
    ToolCapability('metricool.publish', 'metricool', (), 'external_write', 'candidate', 'unavailable', 'paid', ('current_cost', 'write_scope')),
    ToolCapability('vidiq.credit.analyze', 'vidiq', ('youtube',), 'read', 'candidate', 'unavailable', 'credits', ('current_cost',)),
    ToolCapability('mcp.read.assist', 'approved_mcp', (), 'read', 'candidate', 'codex_assisted', 'unknown', ('current_cost', 'read_scope')),
)})


def capabilities_snapshot(account_id: str, registry, *, policy) -> dict:
    from .tool_cost_policy import ToolkitPolicy
    if type(account_id) is not str or not account_id or type(policy) is not ToolkitPolicy:
        raise ValueError('invalid_context')
    connections = []
    for connection in registry.connections.values():
        if connection.account_id == account_id:
            connections.append(dict(account_id=account_id, connection_id=connection.id,
                target_id=connection.target_id, auth_status=connection.auth_status,
                read_scope_status='unknown', write_scope_status='unknown',
                checked_at=connection.auth_checked_at, last_failure=None))
    return dict(account_id=account_id, toolkit_enabled=policy.enabled,
                external_execution_supported=False,
                items=[asdict(item) for item in DEFAULT_CAPABILITIES.values()],
                connections=sorted(connections, key=lambda item: item['connection_id']))
