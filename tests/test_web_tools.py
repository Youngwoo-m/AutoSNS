import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock
from common.operations.content_store import StoreError
spec=importlib.util.spec_from_file_location('web_tools',Path(__file__).resolve().parents[1]/'ax-console/app/web_tools.py')
web=importlib.util.module_from_spec(spec); spec.loader.exec_module(web)
class WebToolsTests(unittest.TestCase):
    def test_exact_routes_and_query(self):
        service=Mock(); service.capabilities.return_value={'status':'ok'}; reader=Mock()
        self.assertEqual(web.handle(service,'GET','/api/v2/tools/capabilities',{'account':['personal']},reader),{'status':'ok'})
        service.capabilities.assert_called_once_with('personal'); reader.assert_not_called()
        for query in ({'account':['personal','dept']},{'provider':['local']},{'account':'personal'}):
            with self.assertRaises(StoreError): web.handle(service,'GET','/api/v2/tools/capabilities',query,reader)
        self.assertFalse(web.recognizes('/api/v2/tools/packaging-preview/'))
        self.assertIsNone(web.handle(service,'GET','/unrelated',{},reader))
    def test_none_service_and_post(self):
        reader=Mock(return_value={'account_id':'personal'})
        result=web.handle(None,'GET','/api/v2/tools/capabilities',{},reader)
        self.assertFalse(result['toolkit_enabled']); reader.assert_not_called()
        with self.assertRaises(StoreError) as caught: web.handle(None,'POST','/api/v2/tools/research-preview',{},reader)
        self.assertEqual(caught.exception.code,'storage_error'); reader.assert_not_called()
        service=Mock(); web.handle(service,'POST','/api/v2/tools/research-preview',{},reader)
        service.research_preview.assert_called_once_with({'account_id':'personal'})
    def test_all_post_routes_and_reject_query_before_body(self):
        service=Mock(); body={'sentinel':'body'}; reader=Mock(return_value=body)
        for suffix,name in web.POST_ROUTES.items():
            result=web.handle(service,'POST',web.BASE+suffix,{},reader)
            getattr(service,name).assert_called_once_with(body)
            with self.assertRaises(StoreError): web.handle(service,'POST',web.BASE+suffix,{'account':['personal']},reader)
        self.assertEqual(reader.call_count,7)
        self.assertIsNone(web.handle(service,'POST',web.BASE+'capabilities',{},reader))
