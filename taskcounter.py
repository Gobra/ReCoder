import time
import threading

from consoleutils import ConsoleUtils
from formatting import Formatting

#---------------------------------------------
# Time tracker
#---------------------------------------------
class TimeTracker:
    def __init__(self, interval=1):
        self.interval = interval
        self.start_time = None
        self.last_report_time = 0

    def start(self):
        self.start_time = time.time()
        self.last_report_time = 0

    def check(self):
        current_time = time.time()
        if current_time - self.last_report_time < self.interval:
            return False
        
        self.last_report_time = current_time
        return True

#---------------------------------------------
# Task counter and reporter
#---------------------------------------------
class TaskCounter:
    def __init__(self, interval=1):
        self.tracker = TimeTracker(interval)
        self.count = 0
        self.lock = threading.Lock()

    def start(self, total, subunits_total=None):
        self.count = 0
        self.total = total
        self.start_time = time.time()
        self.subunits_total = subunits_total
        self.subunits_count = 0

        self.estimated_on = 0
        self.estimate_time = 0

    def increment(self, units=1, subunits=None):
        with self.lock:
            self.count += units

            if self.subunits_total is not None:
                if subunits is None:
                    raise Exception("Subunits are enabled, but no subunits were provided")
                else:
                    self.subunits_count += subunits
    
    def progress(self):
        return self.count / self.total
    
    def report_progress(self, max_length, custom_strings=None):
        # check is report is needed
        if not self.tracker.check():
            return

        # Creates a console progress bar
        # :param progress: Current progress (between 0 and 1)
        # :param max_length: The total length of the progress bar in characters
        # :param path: The path of the last file being processed
        # :param custom_strings: Any lines to print above the progress bar

        # initialize lines array, copy custom strings
        lines = custom_strings.copy() if custom_strings else []

        # calculate progress bar params
        bar = ConsoleUtils.progress_bar_string(self.progress(), max_length)

        # create the progress display string
        time_estimate = self.time_report()
        progress_display = f"[{self.count}/{self.total}] {bar} {self.progress() * 100:.2f}% {time_estimate}\r"
        lines.append(progress_display)

        # Print the progress bar
        with self.lock:
            ConsoleUtils.print_multiline(lines, do_rewind=True)
    
    def time_report(self):
        # use total/count with or without subunits
        subunits = self.subunits_total is not None
        total = self.subunits_total if subunits else self.total
        count = self.subunits_count if subunits else self.count

        with self.lock:
            if count == 0:
                return "Estimating time..."
            elif count != self.estimated_on:
                elapsed_time = time.time() - self.start_time
                average_time_per_task = elapsed_time / count
                remaining_time = average_time_per_task * (total - count)

                self.estimate_time = Formatting.format_time(remaining_time)
                self.estimated_on = count

            return self.estimate_time