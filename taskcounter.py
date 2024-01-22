import time
import threading

#---------------------------------------------
# Task counter and reporter
#---------------------------------------------
class TaskCounter:
    def __init__(self, total, interval=1):
        self.count = 0
        self.total = total
        self.start_time = None
        self.last_report_time = 0
        self.report_interval = interval  # Report interval in seconds
        self.lock = threading.Lock()

    def start(self, total):
        with self.lock:
            self.count = 0
            self.total = total
            self.start_time = time.time()
            self.last_report_time = self.start_time

    def increment(self):
        with self.lock:
            self.count += 1
            current_count = self.count
        return current_count
    
    def progress(self):
        return self.count / self.total
    
    def report_progress(self, max_length):
        """
        Creates a console progress bar.
        
        :param progress: Current progress (between 0 and 1).
        :param max_length: The total length of the progress bar in characters.
        :param file_path: The path of the last file being processed.
        :param max_path_length: Maximum length of the displayed file path.
        """

        current_time = time.time()
        if current_time - self.last_report_time < self.report_interval:
            return
        self.last_report_time = current_time

        # Ensure progress is within bounds
        value = min(max(self.progress(), 0), 1)

        # Calculate the number of '#' characters
        num_hashes = int(value * max_length)

        # Create the bar string
        bar = '#' * num_hashes + '.' * (max_length - num_hashes)

        # Create the progress display string
        time_estimate = self.time_report()
        progress_display = f"[{self.count}/{self.total}] {bar} {value * 100:.2f}% {time_estimate}"

        # Print the progress bar
        print(progress_display, end='\r', flush=True)
    
    def time_report(self):
        with self.lock:
            if self.count == 0:
                return "Estimating time..."
            else:
                elapsed_time = time.time() - self.start_time
                average_time_per_task = elapsed_time / self.count
                remaining_time = average_time_per_task * (self.total - self.count)
                return self.format_time(remaining_time)

    @staticmethod
    def format_time(seconds):
        hours, remainder = divmod(int(seconds), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"