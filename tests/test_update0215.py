"""Tools protocol opens/focuses management mode without a Club launch ticket."""
import ast,re,sys,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from urllib.parse import urlsplit,parse_qs
ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/'client/club_local/web_launch.py').read_text();module=ast.parse(source)
ns={'urlsplit':urlsplit,'parse_qs':parse_qs,'re':re}
parse=next(n for n in module.body if isinstance(n,ast.FunctionDef) and n.name=='parse_launch_link')
exec(compile(ast.Module(body=[parse],type_ignores=[]),'<launch links>','exec'),ns)
window=next(n for n in module.body if isinstance(n,ast.ClassDef) and n.name=='WebLaunchWindow')
handle=next(n for n in window.body if isinstance(n,ast.FunctionDef) and n.name=='handle_run')
exec(compile(ast.Module(body=[handle],type_ignores=[]),'<tools focus>','exec'),ns)

class ToolsTests(unittest.TestCase):
    def test_tools_link_has_no_ticket_and_run_still_requires_a_valid_ticket(self):
        self.assertIsNone(ns['parse_launch_link']('acrclub://tools'))
        self.assertIsNone(ns['parse_launch_link']('acrclub://tools/'))
        self.assertEqual(ns['parse_launch_link']('acrclub://start?ticket='+'a'*43),'a'*43)
        for link in ['acrclub://tools?ticket='+'a'*43,'acrclub://tools#start','acrclub://tools/other','https://tools','acrclub://start','acrclub://user@tools']:
            with self.subTest(link=link),self.assertRaises(ValueError):ns['parse_launch_link'](link)
    def test_tools_focuses_existing_active_window_without_restart_or_api(self):
        root=mock.Mock();api=mock.Mock()
        target=SimpleNamespace(root=root,monitor=SimpleNamespace(status='active',api=api),running=True,restart_link=None)
        ns['handle_run'](target,'acrclub://tools')
        root.deiconify.assert_called_once();root.lift.assert_called_once()
        root.destroy.assert_not_called();api.call.assert_not_called()
        self.assertTrue(target.running);self.assertIsNone(target.restart_link)
    def test_tools_startup_constructs_management_window_with_no_ticket(self):
        node=next(n for n in module.body if isinstance(n,ast.FunctionDef) and n.name=='main')
        root=mock.Mock();factory=mock.Mock(return_value=SimpleNamespace(running=True,restart_link=None))
        context={**ns,'__package__':'club_local','os':SimpleNamespace(name='posix'),'single_instance_lock':lambda:None,'tk':SimpleNamespace(Tk=lambda:root),'WebLaunchWindow':factory}
        sys.path.insert(0,str(ROOT/'client'))
        exec(compile(ast.Module(body=[node],type_ignores=[]),'<tools startup>','exec'),context)
        context['main']('acrclub://tools')
        factory.assert_called_once_with(root,None);root.mainloop.assert_called_once()
