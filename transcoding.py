import math
import os
import re
import subprocess
import multiprocessing

from taskcounter import TaskCounter
from concurrent.futures import ThreadPoolExecutor

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
        self.counter = TaskCounter(0)

    @staticmethod
    def get_codec_info(file_path):
        # get codec information of the video file
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            file_path
        ]

        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return result.stdout.decode().strip()
    
    @staticmethod
    def get_video_length(file_path):
        # get the length of a video using ffprobe
        command = [
            'ffprobe', 
            '-v', 'error', 
            '-show_entries', 'format=duration', 
            '-of', 'default=noprint_wrappers=1:nokey=1', 
            file_path
        ]

        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        duration = result.stdout.strip()
        try:
            return float(duration)
        except ValueError:
            return 0.0
    
    @staticmethod
    def parse_time_to_seconds(time_str):
        h, m, s = map(int, time_str.split(':'))
        return h * 3600 + m * 60 + s
    
    @staticmethod
    def run_ffmpeg_and_process_progress(cmd, file, counter):
        #read the length
        length = VideoTranscoder.get_video_length(file)
        header = f"{file}, total length = {length}"

        with open(os.devnull, 'wb') as devnull:
            process = subprocess.Popen(cmd, stdout=devnull, stderr=subprocess.PIPE, text=True)

            while True:
                line = process.stderr.readline()
                if not line:
                    break

                # Extract the duration and time information
                progress=''
                custom_lines = [header]
                if "time=" in line:
                    time_match = re.search("time=(\d{2}:\d{2}:\d{2})", line)
                    if time_match:
                        current_time = time_match.group(1)
                        custom_lines.append(f" -current time: {current_time}")
                
                # add empty line if we are not reporting progress
                if len(custom_lines) == 1:
                    custom_lines.append("")

                # report
                counter.report_progress(50, custom_strings=custom_lines)

            # wait for the process to finish
            process.wait()

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
        """
        Transcode the video file to AV1 using the SVT-AV1 encoder.
        :param input_path: Path to the input video file.
        :param output_path: Path for the output video file.
        """
        cmd = [
            "ffmpeg", "-i", input_path, "-c:v", "libsvtav1", "-crf", params['crf'], "-b:v", "0",
            "-g", params['gop_size'], "-c:a", "copy", "-row-mt", params['row_mt'],
            "-svtav1-params", f"irefresh-type={params['irefresh_type']}", output_path
        ]
        
        # run syncronously, because ffmpeg prints progress to stderr and also
        # because ffmpeg is using all the CPU cores anyway
        VideoTranscoder.run_ffmpeg_and_process_progress(cmd, input_path, self.counter)

    def transcode_movie(self, entry, params):
        file_path = entry["path"]
        file_dir, file_name = os.path.split(file_path)
        name, ext = os.path.splitext(file_name)
        new_file_path = os.path.join(file_dir, f"{name}_AV1{ext}")
        
        self.transcode_to_av1_svt(file_path, new_file_path, params)

    def transcode_movies(self, movie_files, params=BALANCED):        
        # report how many images are being transcoded
        print(f"Transcoding {len(movie_files)} movies...\n")

        # run
        skipped = []

        self.counter.start(len(movie_files))
        for file in movie_files:
            # check codec is not already AV1
            codec = VideoTranscoder.get_codec_info(file["path"])
            if codec != "av1":
                length = VideoTranscoder.get_video_length(file["path"])
                self.transcode_movie(file, params)
            else:
                skipped.append(file["path"])

            self.counter.increment()

        # report skipped files
        if len(skipped) > 0:
            print(f"\nSkipped files ({len(skipped)}):")
            for file in skipped:
                print(file)

    @staticmethod
    def check_transcoding_validity(file_path, av1_path):
        # check duration
        duration = VideoTranscoder.get_video_length(file_path)
        av1_duration = VideoTranscoder.get_video_length(av1_path)
        return math.isclose(duration, av1_duration, rel_tol=0.01)

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