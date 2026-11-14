"""Optional dependency markers must stay scoped to the selected extra."""
import unittest
import tempfile
from pathlib import Path
from packaging.requirements import Requirement
from tools.verify_distributions import _expected_metadata_fields, _expected_sdist_sidecar_contents


class ConditionalMetadataTests(unittest.TestCase):
    def test_sdist_groups_conditional_dependencies_without_losing_extra_scope(self):
        project={'optional-dependencies':{'research':[
            'base>=1', 'older==2; python_version < "3.12"',
            'newer==3; python_version >= "3.12"',
            'another==4; python_version < "3.12"'],
            'conditional':['only==1; python_version >= "3.12"']}}
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            (root/'src').mkdir()
            actual=_expected_sdist_sidecar_contents(root,set(),'fixture',project)
        self.assertEqual(actual['src/fixture.egg-info/requires.txt'],
            b'\n[conditional]\n\n[conditional:python_version >= "3.12"]\nonly==1\n'
            b'\n[research]\nbase>=1\n\n[research:python_version < "3.12"]\nolder==2\nanother==4\n'
            b'\n[research:python_version >= "3.12"]\nnewer==3\n')

    def test_extra_is_conjoined_with_the_complete_existing_marker(self):
        project={'name':'fixture','version':'1','optional-dependencies':{
            'research':['sample>=1; python_version < "3.12" or platform_system == "Linux"']}}
        value=_expected_metadata_fields(project)['Requires-Dist'][0]
        marker=Requirement(value).marker
        for extra,python,system,expected in (('research','3.11','Windows',True),
                ('research','3.15','Windows',False),('research','3.15','Linux',True),
                ('','3.11','Linux',False),('other','3.11','Windows',False)):
            with self.subTest(extra=extra,python=python,system=system):
                self.assertEqual(marker.evaluate({'extra':extra,'python_version':python,'platform_system':system}),expected)
