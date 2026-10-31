"""Node DOM 시험에 실제 로컬 서비스 응답을 전달한다. 외부 호출/저장 없음."""
import json
from unittest.mock import Mock, patch
from tests.operations.test_local_toolkit import ToolkitTests
from tests.operations.test_research_context import ResearchContextTests
from common.operations.research_context import build_research_preview

fixture=ToolkitTests();fixture.setUp()
packaging=fixture.service.packaging_preview(fixture.packaging())
capabilities=fixture.service.capabilities('all')
fixture.content.read_asset.return_value=({'media_type':'image/png'},b'broken')
image=fixture.service.thumbnail_inspect(dict(content_id='content',revision=2,asset_id='image'))
context=ResearchContextTests().context()
with patch('common.operations.research_context.build_planning_context',return_value=context):
    research=build_research_preview('dept',fixture.registry,Mock(),Mock())
context['destination_metrics'][0]['observation_ids']=[]
with patch('common.operations.research_context.build_planning_context',return_value=context):
    missing=build_research_preview('dept',fixture.registry,Mock(),Mock())
print(json.dumps(dict(packaging=packaging,capabilities=capabilities,image=image,research=research,missing=missing),ensure_ascii=False))
