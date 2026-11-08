import importlib, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
try:evidence=importlib.import_module('evidence')
except ModuleNotFoundError:evidence=None

class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(evidence,'research validator is not implemented')
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.source={'id':'S1','platform':'xiaohongshu','author':'作者','title':'景点体验','url':'https://www.xiaohongshu.com/explore/real-note','captured_at':'2026-11-08','status':'linked_only'}
    def test_link_reference_is_not_a_captured_asset(self):
        self.assertEqual(evidence.validate_sources([self.source],self.root),[])
        self.source['status']='captured'
        self.assertTrue(any('file' in e for e in evidence.validate_sources([self.source],self.root)))
    def test_captured_source_with_real_file_passes(self):
        (self.root/'shot.png').write_bytes(b'file');self.source.update(status='captured',asset_path='shot.png')
        self.assertEqual(evidence.validate_sources([self.source],self.root),[])
    def test_lock_claim_needs_date_and_supplier_evidence(self):
        quote={'id':'Q1','kind':'flight','provider':'FlyAI','checked_at':'2026-11-08','query':{'origin':'北京','destination':'大同'},'price':'400','currency':'CNY','unit':'adult','claim':'locked'}
        errors=evidence.validate_quotes([quote],self.root)
        self.assertTrue(any('date' in e for e in errors));self.assertTrue(any('lock_evidence' in e for e in errors))
    def test_dated_display_price_is_not_required_to_be_a_booking(self):
        quote={'id':'Q1','kind':'hotel','provider':'FlyAI','checked_at':'2026-11-08','query':{'dest_name':'大同','check_in_date':'2027-02-06','check_out_date':'2027-02-08'},'price':'597','currency':'CNY','unit':'room/night','claim':'display','unconfirmed':['房态','儿童早餐']}
        self.assertEqual(evidence.validate_quotes([quote],self.root),[])
    def test_credentials_and_duplicate_source_ids_are_rejected(self):
        self.source['url']+='?key=private-test'
        errors=evidence.validate_sources([self.source,self.source],self.root)
        self.assertTrue(any('credential' in e for e in errors));self.assertTrue(any('duplicate' in e for e in errors))

if __name__=='__main__':unittest.main()
