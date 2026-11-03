from pathlib import Path
import subprocess, math
import av, imageio_ffmpeg

class MediaError(ValueError): pass

def probe(path: Path):
    try:
        with av.open(str(path)) as c:
            streams=c.streams.video
            if not streams: raise MediaError('文件没有视频画面')
            s=streams[0]
            duration=float(s.duration*s.time_base) if s.duration is not None else float(c.duration or 0)/av.time_base
            frame=next(c.decode(s),None)
            if frame is None or not math.isfinite(duration) or duration<=0: raise MediaError('无法读取视频时长或画面')
            return dict(duration=duration,width=frame.width,height=frame.height)
    except (av.error.FFmpegError, StopIteration, OSError, ValueError) as e:
        raise MediaError('视频损坏或编码不支持，请重新选择') from e

def prepare(source: Path, output: Path, poster: Path, start: float, end: float):
    ff=imageio_ffmpeg.get_ffmpeg_exe()
    # FFmpeg honors rotation metadata; scale preserves aspect and limits mobile decode load.
    cmd=[ff,'-y','-nostdin','-loglevel','error','-ss',str(start),'-i',str(source),'-t',str(end-start),'-map','0:v:0','-map','0:a:0?','-vf',"scale=w='min(1280,iw)':h='min(1280,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2",'-c:v','libx264','-preset','veryfast','-crf','23','-pix_fmt','yuv420p','-c:a','aac','-movflags','+faststart',str(output)]
    try:
        subprocess.run(cmd,check=True,capture_output=True,timeout=600)
        subprocess.run([ff,'-y','-nostdin','-loglevel','error','-i',str(output),'-frames:v','1','-vf','scale=320:-2',str(poster)],check=True,capture_output=True,timeout=60)
        return probe(output)
    except (subprocess.SubprocessError, OSError) as e:
        raise MediaError('视频处理失败，可稍后重试或选择其他视频') from e
