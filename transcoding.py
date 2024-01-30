import json
import math
import os
import re
import subprocess
import multiprocessing
import threading

from concurrent.futures import ThreadPoolExecutor
from consoleutils import ConsoleUtils

from formatting import Formatting
from taskcounter import TaskCounter

#---------------------------------------------
# Video transcoding
#---------------------------------------------
class VideoTranscoder:
    # param crf: Constant Rate Factor for video quality.
    # param row_mt: Row-based multithreading setting (1 for enabled, 0 for disabled).
    # param irefresh_type: Intra refresh type setting for the encoder.
    # param gop_size: Size of the Group of Pictures (GOP).
    BALANCED = { 'crf': '21', 'row_mt': '1', 'irefresh_type': '2', 'gop_size': '30' }

    def __init__(self):
        self.db = {}
        self.counter = TaskCounter(0.1)
        self.failed = []
        self.lock = threading.Lock()

    def get_video_info(self, file_path):
        # check db
        with self.lock:
            if file_path in self.db:
                return self.db[file_path]
            
        # query ffprobe
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-show_streams',
            '-show_entries', 'format=duration,stream=codec_name,bit_rate',
            '-of', 'json',
            file_path
        ]

        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        output = json.loads(result.stdout)

        # reset before parsing
        entry = {
            'duration': None,
            'video_codec': None,
            'audio_codec': None,
            'video_bitrate': None,
            'audio_bitrate': None
        }

        # extract duration
        if 'format' in output and 'duration' in output['format']:
            duration_str = output['format']['duration']
            try:
                entry['duration'] = float(duration_str)
            except ValueError:
                entry['duration'] = 0.0
        else:
            entry['duration'] = 0.0

        # extract stream information
        has_video = False
        has_audio = False
        if 'streams' in output:
            for stream in output['streams']:
                if not has_video and (stream['codec_type'] == 'video'):
                    has_video = True
                    entry['video_codec'] = stream.get('codec_name', None)
                    entry['video_bitrate'] = int(stream.get('bit_rate', 0)) if stream.get('bit_rate') else None
                if not has_audio and (stream['codec_type'] == 'audio'):
                    has_audio = True
                    entry['audio_codec'] = stream.get('codec_name', None)
                    entry['audio_bitrate'] = int(stream.get('bit_rate', 0)) if stream.get('bit_rate') else None

                # break if we have both video and audio
                if has_video and has_audio:
                    break

        # save to db
        with self.lock:
            self.db[file_path] = entry

        # done
        return entry
    
    def check_transcoding_validity(self, file_path, av1_path):
        # check duration
        duration = self.get_video_info(file_path)['duration']
        av1_duration = self.get_video_info(av1_path)['duration']
        
        valid = math.isclose(duration, av1_duration, rel_tol=0.01)
        return valid, duration
    
    def _is_audio_codec_supported_in_mp4(self, audio_codec):
        supported_codecs = {'aac', 'mp3', 'ac3', 'eac3'}
        return audio_codec.lower() in supported_codecs
    
    def run_ffmpeg_and_process_progress(self, cmd, file, counter):
        # get info to report basic data
        info = self.get_video_info(file)
        length = info['duration']
        header = f"{file} ({info['video_codec']}, {Formatting.format_time(length)})"

        # check our audio is compressed, mp4 isn't good at storing uncompressed audio
        # formally, it supports raw audio since somewhere 2022, but it reality it will probably fail
        if not self._is_audio_codec_supported_in_mp4(info['audio_codec']):
            # specify the AAC codec and (optionally) set the audio bitrate
            aac_codec_options = ['-c:a', 'aac' ] # '-b:a', '192k' - example bitrate
            # insert the AAC options before the last element (output file)
            cmd = cmd[:-1] + aac_codec_options + cmd[-1:]

        with open(os.devnull, 'wb') as devnull:
            process = subprocess.Popen(cmd, stdout=devnull, stderr=subprocess.PIPE, text=True, bufsize=1, universal_newlines=True)

            last_progress = 0.0
            while True:
                line = process.stderr.readline()
                if not line:
                    break
                if "failed" in line:
                    self.failed.append(file)
                    break

                # Extract the duration and time information
                progress=''
                time_value = 0.0
                custom_lines = [header]
                if "time=" in line:
                    time_match = re.search("time=(\d{2}:\d{2}:\d{2})", line)
                    if time_match:
                        current_time = time_match.group(1)
                        time_value = Formatting.parse_time_to_seconds(current_time)
                        progress = time_value / length
                        bar = ConsoleUtils.progress_bar_string(progress, 25)
                        custom_lines.append(f" -progress: {current_time} {bar} {progress * 100:.2f}%")

                    # add empty line if we are not reporting progress
                    if len(custom_lines) == 1:
                        custom_lines.append("")

                    # report
                    progress = time_value - last_progress
                    last_progress = time_value

                    counter.increment(units=0, subunits=progress)
                    counter.report_progress(50, custom_strings=custom_lines)

            # wait for the process to finish
            process.wait()
            counter.increment(units=1, subunits=0)
            counter.report_progress(50, custom_strings=[""])

    # It works, it's fast, but the output quality is definitely worse than av1_svt,
    # it seems to be a good codec for streaming, but not for archiving
    """def transcode_to_hevc_apple(self, input_path, output_path, quality=65):
        # Transcode the video file to HEVC using Apple's hardware encoder
        # :param input_path: Path to the input video file
        # :param output_path: Path for the output video file
        # :param quality: Quality setting for the encoder
        
        cmd = [
            "ffmpeg", "-i", input_path, "-c:v", "hevc_videotoolbox", "-q:v", str(quality),
            "-tag:v", "hvc1", "-c:a", "copy", output_path
        ]
        subprocess.run(cmd)"""

    def transcode_to_av1_svt(self, input_path, output_path, params):
        # Transcode the video file to AV1 using the SVT-AV1 encoder.
        # :param input_path: Path to the input video file.
        # :param output_path: Path for the output video file.

        # throw exception if output file already exists
        if os.path.exists(output_path):
            raise Exception(f"Output file '{output_path}' already exists")            

        cmd = [
            "ffmpeg", "-i", input_path, "-c:v", "libsvtav1", "-crf", params['crf'], "-b:v", "0",
            "-g", params['gop_size'], "-c:a", "copy", "-row-mt", params['row_mt'],
            "-svtav1-params", f"irefresh-type={params['irefresh_type']}", output_path
        ]
        
        # run syncronously, because ffmpeg prints progress to stderr and also
        # because ffmpeg is using all the CPU cores anyway
        self.run_ffmpeg_and_process_progress(cmd, input_path, self.counter)

    def transcode_movies(self, movie_files, total_duration=None, params=BALANCED):        
        # report how many images are being transcoded
        print(f"Transcoding {len(movie_files)} movies...\n")

        # run
        self.counter.start(len(movie_files), subunits_total=total_duration)
        for file in movie_files:
            file_path = file["path"]
            new_file_path = VideoTranscoder.transcoded_movie_path(file_path)
            self.transcode_to_av1_svt(file_path, new_file_path, params)

        # report failed files
        if len(self.failed) > 0:
            print("Failed files:")
            for file in self.failed:
                print(f" - {file}")

    @staticmethod
    def transcoded_movie_path(file_path):
        file_dir, file_name = os.path.split(file_path)
        name, ext = os.path.splitext(file_name)
        new_file_path = os.path.join(file_dir, f"{name}_AV1.mp4")
        return new_file_path

#---------------------------------------------
# Image transcoding
#---------------------------------------------
class ImageTranscoder:
    QUALITY = {'min': '10', 'max': '20', 'speed': '0', 'depth': '10', 'yuv': '444'}
    BALANCED = {'min': '15', 'max': '25', 'speed': '4', 'depth': '8', 'yuv': '420'}
    SPEED = {'min': '20', 'max': '30', 'speed': '8', 'depth': '8', 'yuv': '420'}

    def __init__(self):
        self.counter = TaskCounter(0)

    def transcode_image_to_avif(self, input_path, output_path, params=BALANCED):
        cmd = ['avifenc']
        for key, value in params.items():
            cmd.extend(['--' + key, value])
        cmd.extend([input_path, output_path])

        with open(os.devnull, 'wb') as devnull:
            subprocess.run(cmd, stdout=devnull, stderr=devnull, check=True)

        self.counter.increment()
        self.counter.report_progress(50, [input_path])

    def transcode_image(self, entry, params):
        file_path = entry["path"]
        file_dir, file_name = os.path.split(file_path)
        name, ext = os.path.splitext(file_name)
        new_file_path = os.path.join(file_dir, f"{name}.avif")
        
        self.transcode_image_to_avif(file_path, new_file_path, params)

    def transcode_images(self, image_files, threads=multiprocessing.cpu_count(), params=BALANCED):
        # report how many images are being transcoded
        print(f"Transcoding {len(image_files)} images, || = {threads}")

        self.counter.start(len(image_files))
        with ThreadPoolExecutor(max_workers=threads) as executor:
            executor.map(self.transcode_image, image_files, [params] * len(image_files))