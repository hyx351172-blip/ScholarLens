import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('record_validation',Path(__file__).parent/'experiments/validate_table_records.py')
protocol=importlib.util.module_from_spec(spec);spec.loader.exec_module(protocol)


class ValidationProtocolTests(unittest.TestCase):
    def test_metadata_adapter_only_falls_back_for_docling(self):
        import sys
        import importlib.metadata as metadata
        sys.path.insert(0,str(Path(__file__).parent/'experiments'))
        from record_validation_compat import distribution_version
        def lookup(name):
            if name=='docling-slim':return '2.117.0'
            raise metadata.PackageNotFoundError(name)
        self.assertEqual(distribution_version('docling',lookup),'2.117.0')
        with self.assertRaises(metadata.PackageNotFoundError):distribution_version('other',lookup)

    def test_excludes_prior_manifest_and_annotation_pages(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'old/prepared').mkdir(parents=True)
            (root/'old/prepared/manifest.json').write_text(json.dumps({'cases':[{'page':'old.png'}]}))
            (root/'old/selected_annotations.json').write_text(json.dumps([{'page_info':{'image_path':'older.png'}}]))
            names,files=protocol.excluded_pages(root)
            self.assertEqual(names,{'old.png','older.png'});self.assertEqual(len(files),2)

    def test_no_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError,'Fresh output'):protocol.prepare(Path(td),12)

    def test_rejected_input_retains_same_fallback(self):
        old,new,a,b=protocol.compare({'gate':{'passed':False,'reasons':['worker failed']}},'baseline')
        self.assertEqual(a,b);self.assertEqual(b,'baseline');self.assertFalse(new['gate']['passed'])

    def test_missing_input_stays_missing_not_dropped(self):
        old,new,a,b=protocol.compare({'gate':{'passed':False,'reasons':['no table']}},None)
        self.assertIsNone(a);self.assertIsNone(b)

if __name__=='__main__':unittest.main()
