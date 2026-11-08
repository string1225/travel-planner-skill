import importlib, json, math, os, struct, subprocess, sys, tempfile, unittest, wave, zlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
try:
    assemble=importlib.import_module('assemble')
except ModuleNotFoundError:
    assemble=None

def png(path,w=320,h=180):
    def chunk(kind,data):return struct.pack('!I',len(data))+kind+data+struct.pack('!I',zlib.crc32(kind+data)&0xffffffff)
    raw=b''.join(b'\0'+bytes([45,125,140])*w for _ in range(h))
    path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',w,h,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b''))

class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(assemble,'media assembler is not implemented')
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        png(self.root/'photo.png')
        self.timeline=[{'id':'day1','start_frame':0,'end_frame':45,'start_ms':0,'end_ms':1500},{'id':'day2','start_frame':45,'end_frame':90,'start_ms':1500,'end_ms':3000}]
        self.manifest={'schema_version':1,'report_dir':'base','media':[{'scene_id':'day1','asset_path':'photo.png','kind':'image','source':{'platform':'original','author':'测试作者','title':'原创测试','captured_at':'2026-11-08'},'usage':{'basis':'original'}}]}
    def test_valid_original_asset(self):
        self.assertEqual(assemble.validate_manifest(self.manifest,self.root,self.timeline),[])
    def test_external_screenshot_requires_source_and_purpose(self):
        self.manifest['media'][0]['source']['platform']='xiaohongshu';self.manifest['media'][0]['usage']={'basis':'quotation'}
        errors=assemble.validate_manifest(self.manifest,self.root,self.timeline)
        self.assertTrue(any('url' in e for e in errors));self.assertTrue(any('purpose' in e for e in errors))
    def test_duplicate_scene_and_missing_file_are_rejected(self):
        self.manifest['media'].append(dict(self.manifest['media'][0],asset_path='missing.png'))
        errors=assemble.validate_manifest(self.manifest,self.root,self.timeline)
        self.assertTrue(any('duplicate' in e for e in errors));self.assertTrue(any('missing' in e for e in errors))
    def test_unknown_scene_and_credentials_in_source_are_rejected(self):
        m=self.manifest['media'][0];m['scene_id']='invented';m['source']['url']='https://restapi.amap.com/map?key=private-test-value'
        errors=assemble.validate_manifest(self.manifest,self.root,self.timeline)
        self.assertTrue(any('unknown scene' in e for e in errors));self.assertTrue(any('credential' in e for e in errors))
    def test_broken_timeline_is_rejected(self):
        self.timeline[1]['start_frame']=46
        self.assertTrue(any('contiguous' in e for e in assemble.validate_manifest(self.manifest,self.root,self.timeline)))
    def test_frame_time_mismatch_is_rejected(self):
        self.timeline[0]['end_ms']=10000
        self.assertTrue(any('frame/time' in e for e in assemble.validate_manifest(self.manifest,self.root,self.timeline)))
    def test_short_clip_needs_explicit_hold(self):
        with self.assertRaisesRegex(ValueError,'short'):
            assemble.clip_timing({'clip_start':0,'clip_end':1},source_duration=2,scene_duration=1.5)
        self.assertAlmostEqual(assemble.clip_timing({'clip_start':0,'clip_end':1,'hold_last_frame':True},2,1.5)['hold_seconds'],0.5)
    def test_clip_end_cannot_exceed_real_duration(self):
        with self.assertRaisesRegex(ValueError,'duration'):
            assemble.clip_timing({'clip_start':0,'clip_end':6},5,1.5)
    def test_video_needs_explicit_bounds(self):
        with self.assertRaisesRegex(ValueError,'explicit'):
            assemble.clip_timing({},20,3)
    def test_nested_credential_field_is_not_saved_as_source(self):
        self.manifest['media'][0]['source']['cookie']='fake-private-cookie'
        self.assertTrue(any('credential' in e for e in assemble.validate_manifest(self.manifest,self.root,self.timeline)))

class MixedVideoTest(unittest.TestCase):
    def test_real_image_and_clip_keep_frames_audio_and_original(self):
        self.assertIsNotNone(assemble,'media assembler is not implemented')
        tools=assemble.media_tools()
        if not tools['ffmpeg'] or not tools['ffprobe']:self.skipTest('FFmpeg/ffprobe not installed')
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);base=root/'base';(base/'frames').mkdir(parents=True)
            for name in ['photo.png','frames/001-day1.png','frames/002-day2.png','frames/003-day3.png']:png(root/name if name=='photo.png' else base/name)
            (base/'video.mp4').write_bytes(b'original-do-not-overwrite')
            scenes=[{'id':'day1','title':'图文：保留整个画面'},{'id':'day2','title':'片段：保持原始比例'},{'id':'day3','title':'原始画面保留'}]
            timeline=[{'id':'day1','start_frame':0,'end_frame':45,'start_ms':0,'end_ms':1500},{'id':'day2','start_frame':45,'end_frame':90,'start_ms':1500,'end_ms':3000},{'id':'day3','start_frame':90,'end_frame':135,'start_ms':3000,'end_ms':4500}]
            (base/'report.json').write_text(json.dumps({'title':'混合样片','fps':30,'scenes':scenes}),encoding='utf8')
            (base/'timeline.json').write_text(json.dumps(timeline),encoding='utf8')
            (base/'captions.json').write_text(json.dumps([{'start_ms':100,'end_ms':2800,'text':'完整句子保留在同一条字幕。'}]),encoding='utf8')
            (base/'subtitles.ass').write_text('[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\n[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\nStyle: Default,Microsoft YaHei,46,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,0,2,100,100,72,1\n[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\nDialogue: 0,0:00:00.10,0:00:02.80,Default,,0,0,0,,完整句子保留在同一条字幕。\n',encoding='utf8')
            with wave.open(str(base/'voice.wav'),'wb') as audio:
                audio.setparams((1,2,48000,0,'NONE','not compressed'));audio.writeframes(b''.join(struct.pack('<h',int(3000*math.sin(2*math.pi*440*i/48000))) for i in range(216000)))
            subprocess.run([tools['ffmpeg'],'-v','error','-y','-f','lavfi','-i','testsrc2=size=240x320:rate=30','-t','2','-c:v','libx264','-pix_fmt','yuv420p',str(root/'clip.mp4')],check=True,capture_output=True)
            source={'platform':'original','author':'本地测试','title':'原创测试素材','captured_at':'2026-11-08'}
            manifest={'schema_version':1,'report_dir':'base','media':[{'scene_id':'day1','asset_path':'photo.png','kind':'image','source':source,'usage':{'basis':'original'}},{'scene_id':'day2','asset_path':'clip.mp4','kind':'video','clip_start':0.2,'clip_end':1.8,'source':source,'usage':{'basis':'original'}}]}
            path=root/'media.json';path.write_text(json.dumps(manifest),encoding='utf8')
            qa=assemble.build(path,root/'mixed',tools=tools)
            self.assertTrue(qa['passed']);self.assertEqual(qa['frames'],135);self.assertEqual(qa['dimensions'],[1920,1080]);self.assertTrue(qa['full_decode']);self.assertEqual(qa['original_scenes'],1)
            self.assertEqual((base/'video.mp4').read_bytes(),b'original-do-not-overwrite')
            self.assertTrue((root/'mixed/deck/index.html').is_file());saved_manifest=json.loads((root/'mixed/media-manifest.json').read_text(encoding='utf8'));self.assertEqual(len(saved_manifest['media']),2)
            clip_info=assemble.probe(root/'mixed'/saved_manifest['media'][1]['asset_path'],tools['ffprobe'])
            self.assertLess(float(clip_info['format']['duration']),1.7)
            self.assertFalse(any(s['codec_type']=='audio' for s in clip_info['streams']))
            self.assertEqual(saved_manifest['report_dir'],'.')
            (base/'voice.wav').unlink();(root/'photo.png').unlink();(root/'clip.mp4').unlink()
            rebuilt=assemble.build(root/'mixed/media-manifest.json',root/'rebuilt',tools=tools)
            self.assertTrue(rebuilt['passed']);self.assertEqual(rebuilt['frames'],135)
            rebuilt_manifest=json.loads((root/'rebuilt/media-manifest.json').read_text(encoding='utf8'))
            self.assertEqual(rebuilt_manifest['media'][1]['source'],saved_manifest['media'][1]['source'])
            if os.environ.get('TRAVEL_TEST_ARTIFACTS'):
                import shutil;dest=Path(os.environ['TRAVEL_TEST_ARTIFACTS']);shutil.copytree(root/'mixed',dest,dirs_exist_ok=True)

if __name__=='__main__':unittest.main()
