"""Prepare mono 16k WAV/MP3 for ASR without modifying the original media."""
import argparse
import json
from pathlib import Path
import subprocess
from bailian_media import save, file_hash, tool_path

MIME_TYPES = {'.wav': 'audio/wav', '.mp3': 'audio/mpeg'}


def prepare(media, output, ffmpeg=None):
    ffmpeg = ffmpeg or tool_path('ffmpeg')
    media, output = Path(media).resolve(), Path(output).resolve()
    if not media.is_file():
        raise ValueError('Input media missing')
    if media == output or output.suffix.lower() not in MIME_TYPES:
        raise ValueError('Use a separate .wav or .mp3 output path')
    output.parent.mkdir(parents=True, exist_ok=True)
    codec = ['-c:a', 'pcm_s16le'] if output.suffix.lower() == '.wav' else ['-c:a', 'libmp3lame', '-b:a', '128k']
    subprocess.run([str(ffmpeg), '-y', '-v', 'error', '-i', str(media), '-map', '0:a:0',
                    '-vn', '-ac', '1', '-ar', '16000', *codec, str(output)],
                   check=True, capture_output=True)
    if output.stat().st_size > 256 * 1024 * 1024:
        raise ValueError('Audio exceeds 256 MiB adapter cap; split with recorded source offsets')
    result = {'source': str(media), 'audio': str(output), 'source_offset_s': 0,
              'sample_rate': 16000, 'channels': 1, 'mime_type': MIME_TYPES[output.suffix.lower()],
              'size_bytes': output.stat().st_size, 'audio_sha256': file_hash(output)}
    save(output.with_suffix(output.suffix + '.json'), result)
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--media', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True, help='Output .wav or .mp3 file')
    p.add_argument('--ffmpeg', default=None, help='Defaults to the resolved ffmpeg (see bootstrap.py)')
    a = p.parse_args()
    try:
        print(json.dumps(prepare(a.media, a.out, a.ffmpeg), ensure_ascii=False))
    except (ValueError, OSError, subprocess.CalledProcessError) as e:
        p.exit(1, str(e) + '\n' if isinstance(e, ValueError) else 'Audio preparation failed; check input and FFmpeg\n')
