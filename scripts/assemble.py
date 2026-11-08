"""Compose attributed travel images/clips on a video-report frame timeline."""
from __future__ import annotations
import argparse, json, math, os, re, shutil, subprocess, textwrap, time, wave
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from evidence import credential_paths

W,H=1920,1080
SECRET_QUERY={'key','api_key','apikey','token','access_token','csrf','sessdata','xsec_token'}
BASE_FILES=['report.json','timeline.json','captions.json','subtitles.ass','voice.wav']

def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def write(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
def resolve(root,path):return (Path(root)/path).resolve()

def media_tools():
    roots=[]
    for parent in [Path(os.environ.get('CODEX_HOME',Path.home()/'.codex'))/'skills',Path.home()/'.agents/skills']:
        skill=parent/'video-report'
        if skill.exists():roots.append(skill.resolve().parent.parent)
    def locate(name,env):
        candidates=[os.environ.get(env),shutil.which(name)]
        candidates += [str(p/'.tools/bin'/(name+'.exe' if os.name=='nt' else name)) for p in roots]
        return next((str(Path(p).resolve()) for p in candidates if p and Path(p).is_file()),None)
    font_candidates=[os.environ.get('TRAVEL_FONT'),str(Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts/msyh.ttc'),'/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc','/System/Library/Fonts/PingFang.ttc']
    return {'ffmpeg':locate('ffmpeg','VIDEO_REPORT_FFMPEG'),'ffprobe':locate('ffprobe','VIDEO_REPORT_FFPROBE'),'font':next((p for p in font_candidates if p and Path(p).is_file()),None)}

def validate_manifest(data,root,timeline,fps=30):
    errors=['credential field or URL at '+p for p in credential_paths(data)]
    if data.get('schema_version')!=1:errors.append('schema_version must be 1')
    media=data.get('media')
    if not isinstance(media,list):return errors+['media must be an array']
    ids={t.get('id') for t in timeline};last=0;seen=set()
    if not timeline:errors.append('timeline must not be empty')
    if len(ids)!=len(timeline):errors.append('duplicate timeline scene id')
    for t in timeline:
        if t.get('start_frame')!=last or not isinstance(t.get('end_frame'),int) or t.get('end_frame',0)<=last:
            errors.append('timeline must have contiguous positive frame intervals')
        last=t.get('end_frame',last)
        for stamp,frame in [('start_ms','start_frame'),('end_ms','end_frame')]:
            if stamp in t and (not isinstance(t[stamp],(int,float)) or not math.isfinite(t[stamp]) or abs(t[stamp]-t.get(frame,0)*1000/fps)>1000/fps+0.1):
                errors.append('timeline frame/time boundaries disagree')
    for i,m in enumerate(media):
        prefix=f'media[{i}]'
        if not isinstance(m,dict):errors.append(prefix+' must be an object');continue
        sid=m.get('scene_id')
        if sid not in ids:errors.append(prefix+' unknown scene')
        if sid in seen:errors.append(prefix+' duplicate scene')
        seen.add(sid)
        if m.get('kind') not in {'image','video'}:errors.append(prefix+' kind must be image or video')
        if m.get('kind')=='video' and any(k not in m for k in ['clip_start','clip_end']):errors.append(prefix+' video requires explicit clip_start and clip_end')
        asset=m.get('asset_path')
        if not isinstance(asset,str) or not resolve(root,asset).is_file():errors.append(prefix+' asset file missing')
        source=m.get('source') or {};usage=m.get('usage') or {}
        for key in ['platform','author','title','captured_at']:
            if not isinstance(source.get(key),str) or not source[key].strip():errors.append(prefix+' source.'+key+' required')
        external=source.get('platform')!='original'
        if external:
            url=source.get('url','');parsed=urlparse(url)
            if parsed.scheme not in {'https','http'} or not parsed.netloc:errors.append(prefix+' source.url required')
            if usage.get('basis') not in {'permission','license','quotation'}:errors.append(prefix+' external usage basis required')
            if usage.get('basis')=='quotation' and not str(usage.get('purpose','')).strip():errors.append(prefix+' quotation purpose required')
            if usage.get('basis') in {'permission','license'} and not str(usage.get('evidence','')).strip():errors.append(prefix+' rights evidence required')
        elif usage.get('basis')!='original':errors.append(prefix+' original usage basis required')
        query=parse_qs(urlparse(source.get('url','')).query)
        if SECRET_QUERY.intersection(k.lower() for k in query):errors.append(prefix+' source URL contains credential parameter; use canonical public link')
        if any(k.lower() in SECRET_QUERY for k in m):errors.append(prefix+' contains credential field')
    return errors

def clip_timing(media,source_duration,scene_duration):
    if any(k not in media for k in ['clip_start','clip_end']):raise ValueError('video requires explicit clip_start and clip_end')
    start=float(media.get('clip_start',0));end=float(media.get('clip_end',source_duration))
    if not all(math.isfinite(x) for x in [start,end,source_duration,scene_duration]) or start<0 or end<=start or end>source_duration+0.001:
        raise ValueError('clip boundaries exceed source duration or are invalid')
    available=end-start;hold=max(0,scene_duration-available)
    if hold>0.001 and media.get('hold_last_frame') is not True:raise ValueError('clip is too short; shorten narration or explicitly set hold_last_frame')
    return {'start':start,'take_seconds':min(available,scene_duration),'hold_seconds':hold}

def run(argv,cwd=None,timeout=300):
    result=subprocess.run([str(x) for x in argv],cwd=cwd,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:raise RuntimeError('Media command failed: '+result.stderr[-2200:])
    return result.stdout

def probe(path,ffprobe,count=False):
    args=[ffprobe,'-v','error']+(['-count_frames'] if count else [])
    return json.loads(run(args+['-show_streams','-show_format','-of','json',path]))

def label_for(m,index):
    s=m['source'];label=f"S{index:02d} · {s['platform']} · {s['author']} · {s['title']}"
    if m.get('hold_last_frame'):label+='（短片后停留末帧）'
    return '\n'.join(textwrap.wrap(label[:145]+('…' if len(label)>145 else ''),width=76))

def write_preview(output,report,timeline,visuals,captions):
    payload=json.dumps({'report':report,'timeline':timeline,'visuals':visuals,'captions':captions},ensure_ascii=False).replace('<','\\u003c')
    template=(Path(__file__).resolve().parents[1]/'assets/mixed-preview.html').read_text(encoding='utf-8')
    deck=output/'deck';deck.mkdir(exist_ok=True)
    (deck/'index.html').write_text(template.replace('__DATA__',payload),encoding='utf-8')

def build(manifest_path,output,tools=None,overwrite=False):
    started=time.monotonic();manifest_path=Path(manifest_path).resolve();root=manifest_path.parent;data=read(manifest_path)
    base=resolve(root,data['report_dir']);output=Path(output).resolve()
    if base==output:raise ValueError('output must differ from report_dir to preserve the original video')
    for name in BASE_FILES:
        if not (base/name).is_file():raise ValueError('video-report artifact missing: '+name)
    report=read(base/'report.json');timeline=read(base/'timeline.json');captions=read(base/'captions.json')
    fps=int(report.get('fps',30))
    if fps<=0:raise ValueError('fps must be positive')
    errors=validate_manifest(data,root,timeline,fps)
    if errors:raise ValueError('; '.join(errors))
    if not timeline:raise ValueError('timeline is empty')
    if fps<=0 or [report.get('width',W),report.get('height',H)]!=[W,H]:raise ValueError('mixed compositor currently requires a 1920x1080 video-report base')
    timeline=[dict(t,start_ms=t['start_frame']*1000/fps,end_ms=t['end_frame']*1000/fps,duration_ms=(t['end_frame']-t['start_frame'])*1000/fps) for t in timeline]
    total=timeline[-1]['end_frame'];seconds=total/fps
    with wave.open(str(base/'voice.wav'),'rb') as voice:
        if abs(voice.getnframes()/voice.getframerate()-seconds)>1/fps+0.001:raise ValueError('voice duration does not match frame timeline')
    tools=tools or media_tools()
    if not all(tools.get(k) for k in ['ffmpeg','ffprobe','font']):raise ValueError('FFmpeg, ffprobe and a CJK font are required; run dependencies.py doctor')
    if (output/'video.mp4').exists() and not overwrite:raise ValueError('output video already exists; choose another output or pass --overwrite')
    output.mkdir(parents=True,exist_ok=True);work=output/'work';work.mkdir(exist_ok=True);media_dir=output/'media';media_dir.mkdir(exist_ok=True)
    shutil.copy2(tools['font'],work/'font.ttc')
    by_id={m['scene_id']:m for m in data['media']};scene_by_id={s['id']:s for s in report['scenes']}
    visuals=[];used=[]
    for i,t in enumerate(timeline):
        sid=t['id'];frames=t['end_frame']-t['start_frame'];duration=frames/fps;m=by_id.get(sid)
        if sid not in scene_by_id:raise ValueError('timeline scene missing in report: '+sid)
        title=scene_by_id[sid]['title'];segment=f'scene-{i:03d}.mp4'
        if m:
            src=resolve(root,m['asset_path']);dest=media_dir/f'asset-{i:03d}{".mp4" if m["kind"]=="video" else ".png"}'
            title_lines=textwrap.wrap(title.replace('\n',' '),width=36)
            if len(title_lines)>2:raise ValueError('scene title exceeds two lines; shorten it: '+sid)
            title_file=f'title-{i:03d}.txt';label_file=f'source-{i:03d}.txt'
            (work/title_file).write_text('\n'.join(title_lines),encoding='utf-8');label=label_for(m,i+1);(work/label_file).write_text(label,encoding='utf-8')
            filters=[f'fps={fps}','setpts=PTS-STARTPTS','scale=1728:660:force_original_aspect_ratio=decrease','pad=1728:660:(ow-iw)/2:(oh-ih)/2:color=0xe4ece8','pad=1920:1080:96:160:color=0xf5f2ea']
            args=[tools['ffmpeg'],'-v','error','-y'];timing=None
            if m['kind']=='image':
                run([tools['ffmpeg'],'-v','error','-y','-i',src,'-frames:v','1',dest])
                args+=['-loop','1','-framerate',str(fps),'-i',dest]
            else:
                info=probe(src,tools['ffprobe']);timing=clip_timing(m,float(info['format']['duration']),duration)
                run([tools['ffmpeg'],'-v','error','-y','-ss',str(timing['start']),'-t',str(timing['take_seconds']),'-i',src,'-vf',f'fps={fps},setpts=PTS-STARTPTS','-an','-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p',dest],timeout=max(120,duration*6))
                args+=['-i',dest]
                if timing['hold_seconds']:filters.append(f"tpad=stop_mode=clone:stop_duration={timing['hold_seconds']+1/fps}")
            filters += [f'drawtext=fontfile=font.ttc:textfile={title_file}:expansion=none:fontcolor=0x153742:fontsize=44:line_spacing=4:x=96:y=40',f'drawtext=fontfile=font.ttc:textfile={label_file}:expansion=none:fontcolor=0x49666d:fontsize=20:line_spacing=4:x=96:y=854']
            run(args+['-vf',','.join(filters),'-an','-frames:v',str(frames),'-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p',segment],cwd=work,timeout=max(120,duration*6))
            item=dict(m,asset_path=dest.relative_to(output).as_posix())
            if timing:
                original_start=float(m['source'].get('original_clip_start',0))+timing['start']
                item.update(clip_start=0,clip_end=float(probe(dest,tools['ffprobe'])['format']['duration']),source=dict(m['source'],original_clip_start=original_start,original_clip_end=original_start+timing['take_seconds']))
            used.append(item)
            visuals.append({'kind':m['kind'],'path':'../'+dest.relative_to(output).as_posix(),'title':title,'label':label,'clip_start':0,'clip_end':item.get('clip_end',0),'fallback':False})
        else:
            safe=re.sub(r'[^A-Za-z0-9_-]','_',sid)[:60];frame=base/'frames'/f'{i+1:03d}-{safe}.png'
            if not frame.is_file():raise ValueError('original scene frame missing: '+sid)
            dest=media_dir/f'original-{i:03d}.png';shutil.copy2(frame,dest)
            (output/'frames').mkdir(exist_ok=True);shutil.copy2(frame,output/'frames'/frame.name)
            run([tools['ffmpeg'],'-v','error','-y','-loop','1','-framerate',str(fps),'-i',dest,'-vf',f'scale={W}:{H},setsar=1','-an','-frames:v',str(frames),'-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p',segment],cwd=work,timeout=max(120,duration*6))
            visuals.append({'kind':'image','path':'../'+dest.relative_to(output).as_posix(),'fallback':True})
        actual=probe(work/segment,tools['ffprobe'],count=True)
        v=next(s for s in actual['streams'] if s['codec_type']=='video')
        if int(v.get('nb_read_frames',0))!=frames:raise ValueError('source produced too few frames: '+sid)
    for name in BASE_FILES:shutil.copy2(base/name,output/name)
    write(output/'timeline.json',timeline)
    for name in ['subtitles.srt','storyboard.md','sources.json','costs.json']:
        if (base/name).exists():shutil.copy2(base/name,output/name)
    shutil.copy2(base/'subtitles.ass',work/'captions.ass')
    (work/'concat.txt').write_text('\n'.join(f"file 'scene-{i:03d}.mp4'" for i in range(len(timeline))),encoding='utf-8')
    run([tools['ffmpeg'],'-v','error','-y','-f','concat','-safe','1','-i','concat.txt','-i',output/'voice.wav','-map','0:v:0','-map','1:a:0','-vf','ass=captions.ass','-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p','-frames:v',str(total),'-c:a','aac','-ar','48000','-movflags','+faststart',output/'video.mp4'],cwd=work,timeout=max(180,seconds*8))
    info=probe(output/'video.mp4',tools['ffprobe'],count=True);v=next(s for s in info['streams'] if s['codec_type']=='video');a=next(s for s in info['streams'] if s['codec_type']=='audio')
    run([tools['ffmpeg'],'-v','error','-i',output/'video.mp4','-f','null','-'],timeout=max(120,seconds*3))
    qa={'passed':int(v.get('nb_read_frames',0))==total and [v['width'],v['height']]==[W,H],'full_decode':True,'frames':int(v.get('nb_read_frames',0)),'expected_frames':total,'dimensions':[v['width'],v['height']],'duration_seconds':float(info['format']['duration']),'audio_codec':a['codec_name'],'media_scenes':len(used),'original_scenes':len(timeline)-len(used),'visual_review':'not_performed','listening':'not_performed','assembly_seconds':round(time.monotonic()-started,2)}
    write(output/'media-manifest.json',dict(data,report_dir='.',media=used));write(output/'mixed-qa.json',qa)
    write_preview(output,report,timeline,visuals,captions)
    if not qa['passed']:raise ValueError('mixed video failed frame/dimension checks')
    return qa

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['validate','build']);p.add_argument('manifest',type=Path);p.add_argument('--output',type=Path);p.add_argument('--overwrite',action='store_true');a=p.parse_args()
    try:
        if a.command=='validate':
            data=read(a.manifest);base=resolve(a.manifest.resolve().parent,data['report_dir']);errors=validate_manifest(data,a.manifest.resolve().parent,read(base/'timeline.json'),int(read(base/'report.json').get('fps',30)))
            print(json.dumps({'valid':not errors,'errors':errors},ensure_ascii=False));return int(bool(errors))
        if not a.output:p.error('build requires --output')
        print(json.dumps(build(a.manifest,a.output,overwrite=a.overwrite),ensure_ascii=False));return 0
    except (ValueError,KeyError,OSError,RuntimeError,subprocess.TimeoutExpired) as e:
        print(json.dumps({'error':str(e)},ensure_ascii=False));return 1

if __name__=='__main__':raise SystemExit(main())
