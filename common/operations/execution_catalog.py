"""서버가 등록하는 실행 명세. 조회/검증은 파일과 프로세스를 열지 않는다."""
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
import re
from .models import ContractError, freeze


def _names(value):
    return isinstance(value, (tuple, list)) and all(isinstance(x, str) and x for x in value) and len(set(value)) == len(value)


@dataclass(frozen=True)
class ExecutorSpec:
    id: str
    job_ids: tuple
    phases: tuple
    interpreter: str
    cwd: Path
    module: str
    mutation_actions: tuple
    environment_names: tuple

    def __post_init__(self):
        if (not isinstance(self.id, str) or not self.id or
            not isinstance(self.interpreter, (str, Path)) or not Path(self.interpreter).is_absolute() or
            not isinstance(self.cwd, (str, Path)) or not Path(self.cwd).is_absolute() or
            not isinstance(self.module, str) or not re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*', self.module)):
            raise ContractError('invalid_catalog')
        for name in ('job_ids', 'phases', 'mutation_actions', 'environment_names'):
            value = getattr(self, name)
            if not _names(value):
                raise ContractError('invalid_catalog')
            object.__setattr__(self, name, tuple(value))
        if not self.job_ids or not self.phases or not set(self.phases) <= {'prepare', 'submit', 'verify'}:
            raise ContractError('invalid_catalog')
        if any(not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name) for name in self.environment_names):
            raise ContractError('invalid_catalog')
        object.__setattr__(self, 'interpreter', str(self.interpreter))
        object.__setattr__(self, 'cwd', Path(self.cwd))


@dataclass(frozen=True)
class ExecutionCatalog:
    executors: Mapping = field(default_factory=dict)
    callers: Mapping = field(default_factory=dict)
    production_jobs: Mapping = field(default_factory=dict)

    def __post_init__(self):
        for name in ('executors', 'callers', 'production_jobs'):
            value = getattr(self, name)
            if not isinstance(value, Mapping) or not all(isinstance(key, str) and key for key in value):
                raise ContractError('invalid_catalog')
        for key, executor in self.executors.items():
            if not isinstance(executor, ExecutorSpec) or executor.id != key:
                raise ContractError('invalid_catalog')
        for caller in self.callers.values():
            if (not isinstance(caller, Mapping) or set(caller) != {'job_ids', 'source', 'legacy_allowed'} or
                not _names(caller['job_ids']) or caller['source'] not in ('console', 'launchd') or
                type(caller['legacy_allowed']) is not bool):
                raise ContractError('invalid_catalog')
        if not all(isinstance(value, Mapping) for value in self.production_jobs.values()):
            raise ContractError('invalid_catalog')
        for name in ('executors', 'callers', 'production_jobs'):
            object.__setattr__(self, name, freeze(getattr(self, name)))
