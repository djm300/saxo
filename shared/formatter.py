import logging

# Define emojis for different log levels
LOG_EMOJIS = {
    logging.DEBUG: "🐛",
    logging.INFO: "✅",
    logging.WARNING: "⚠️",
    logging.ERROR: "❌",
    logging.CRITICAL: "🔥",
}

# Define ANSI escape codes for colors
LOG_COLORS = {
    logging.DEBUG: "\033[94m",  # Blue
    logging.INFO: "\033[92m",   # Green
    logging.WARNING: "\033[93m", # Yellow
    logging.ERROR: "\033[91m",  # Red
    logging.CRITICAL: "\033[91m", # Red
}
RESET_COLOR = "\033[0m"

# ==============================
# Logging setup
# ==============================
# Use a custom formatter to include module name, color, and emoji
class CustomFormatter(logging.Formatter):
    def format(self, record):
        emoji = LOG_EMOJIS.get(record.levelno, "❓")
        color_start = LOG_COLORS.get(record.levelno, "")
        color_end = RESET_COLOR if color_start else ""

        # Extract the module name (last part of logger name)
        module_name = record.name.split('.')[-1]

        # Format timestamp as HH:MM:SS
        timestamp = self.formatTime(record, "%H:%M:%S")

        # New format: [LEVEL] MODULE - HH:MM:SS EMOJI - MESSAGE
        log_message = (
            f"[{color_start}{record.levelname:<8}{RESET_COLOR}] "
            f"{color_start}{record.filename:<15}{RESET_COLOR}"
            f"{color_start}{record.funcName:<15}{RESET_COLOR}"
            f"{timestamp} {emoji} - "
            f"{color_start}{record.getMessage()}{color_end}"
        )

        return log_message