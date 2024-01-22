import time
import threading

#---------------------------------------------
# Task counter and reporter
#---------------------------------------------
class TaskCounter:
    def __init__(self, interval=1, subunits=False):
        self.count = 0
        self.start_time = None
        self.last_report_time = 0
        self.report_interval = interval  # report interval in seconds
        self.subunits = subunits         # if true, we will use subunits to estimate completion time
        self.lock = threading.Lock()

    def start(self, total, subunits_total=None):
        self.count = 0
        self.subunits_count = 0
        self.total = total
        self.subunits_total = subunits_total
        self.start_time = time.time()

        self.estimated_on = 0
        self.estimate_time = 0

        self.last_report_time = self.start_time

    def increment(self, subunits=None):
        with self.lock:
            self.count += 1

            if self.subunits:
                if subunits is None:
                    raise Exception("Subunits are enabled, but no subunits were provided")
                else:
                    self.subunits_count += subunits
    
    def progress(self):
        return self.count / self.total
    
    def report_progress(self, max_length, custom_strings=None):
        # check is report is needed
        current_time = time.time()
        if current_time - self.last_report_time < self.report_interval:
            return
        self.last_report_time = current_time

        # Creates a console progress bar
        # :param progress: Current progress (between 0 and 1)
        # :param max_length: The total length of the progress bar in characters
        # :param path: The path of the last file being processed
        # :param custom_strings: Any lines to print above the progress bar

        # initialize lines array, copy custom strings
        lines = custom_strings.copy() if custom_strings else []

        # calculate progress bar params
        value = min(max(self.progress(), 0), 1)                     # ensure progress is within bounds
        num_hashes = int(value * max_length)                        # calculate the number of '#' characters
        bar = '#' * num_hashes + '.' * (max_length - num_hashes)    # create the bar string

        # create the progress display string
        time_estimate = self.time_report()
        progress_display = f"[{self.count}/{self.total}] {bar} {value * 100:.2f}% {time_estimate}\r"
        lines.append(progress_display)

        # ANSI escape codes:
        # \x1b[2K   - clear the current line
        # \x1b[A    - move cursor up one line
        # \r        - move cursor to the beginning of the line

        # create a single string from the lines array, with:
        # - each line starting with a clear line command
        # - each line separated by a newline
        # - the cursor moved up lines.count times at the end and the cursor moved to the beginning of the line
        builder = ""
        rewind = "\r"
        for line in lines:
            builder += f"\x1b[2K{line}\n"
            rewind = "\x1b[A" + rewind
        custom_display = builder + rewind

        # Print the progress bar
        with self.lock:
            print(custom_display, end='', flush=True)
    
    def time_report(self):
        # use total/count with or without subunits
        total = self.subunits_total if not self.subunits else self.total
        count = self.subunits_count if not self.subunits else self.count

        with self.lock:
            if count == 0:
                return "Estimating time..."
            elif count != self.estimated_on:
                elapsed_time = time.time() - self.start_time
                average_time_per_task = elapsed_time / count
                remaining_time = average_time_per_task * (total - count)

                self.estimate_time = self.format_time(remaining_time)
                self.estimated_on = count

            return self.estimate_time

    @staticmethod
    def format_time(seconds):
        hours, remainder = divmod(int(seconds), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"