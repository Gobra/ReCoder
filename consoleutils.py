class ConsoleUtils:
    UP = "\x1b[A"       # move cursor up one line
    CLEAR = "\x1b[2K"   # clear the current line
    REWIND = "\r"       # move cursor to the beginning of the line

    @staticmethod
    def print_multiline(lines, do_rewind=True):
        # create a single string from the lines array, with:
        # - each line starting with a clear line command
        # - each line separated by a newline
        # - the cursor moved up lines.count times at the end and the cursor moved to the beginning of the line
        builder = ""
        rewind = "\r" if do_rewind else ""
        for line in lines:
            builder += f"{ConsoleUtils.CLEAR}{line}\n"
            if do_rewind:
                rewind = ConsoleUtils.UP + rewind
        custom_display = builder + rewind

        # print
        print(custom_display, end='' if do_rewind else '\n', flush=True)

    @staticmethod
    def print_and_rewind(line):
        # print a line and move the cursor to the beginning of the line
        ConsoleUtils.print_multiline([line], do_rewind=True)

    @staticmethod
    def clear_lines(count):
        lines = " " * count
        ConsoleUtils.print_multiline(lines, do_rewind=True)

    @staticmethod
    def progress_bar_string(progress, max_length):
        # Creates a console progress bar
        # :param progress: Current progress (between 0 and 1)
        # :param max_length: The total length of the progress bar in characters

        # calculate progress bar params
        value = min(max(progress, 0), 1)                            # ensure progress is within bounds
        num_hashes = int(value * max_length)                        # calculate the number of '#' characters
        bar = '#' * num_hashes + '.' * (max_length - num_hashes)    # create the bar string
        return bar