import threading
import time
import logging
from datetime import datetime, timedelta
from cronsim import CronSim # Import CronSim

# Assuming saxo_sdk is accessible in the Python path
from saxo_sdk.client import SaxoClient
from .config import Config
logger = logging.getLogger()


class OrderScheduler:
    def __init__(self, client: SaxoClient, config: Config):
        self.saxo_client = client # Access SaxoClient
        self.cron_expression = config.ORDER_SCHEDULE_TIME # Now expects a cron expression
        self.order_details = config.ORDER_DETAILS
        self._scheduler_thread = None
        self._stop_event = threading.Event()


    def _place_order(self):
        # The SaxoClient instance already handles token management internally.
        # We just need to call its place_order method.
        logger.info(f"Attempting to place order: {self.order_details}")
        try:
            order_response = self.saxo_client.place_order(self.order_details)
            logger.info(f"Order placed successfully: {order_response}")
        except Exception as e:
            logger.error(f"Failed to place order: {e}")

    def _schedule_loop(self):
        while not self._stop_event.is_set():

            # Calculate next schedule_time using cronsim
            cron = CronSim(self.cron_expression, datetime.now())
            schedule_time = next(cron)

            # Calculate time to wait until the scheduled time
            time_to_wait = (schedule_time - datetime.now()).total_seconds()
            logger.info(f"Next order scheduled for: {schedule_time.strftime('%Y-%m-%d %H:%M:%S')}. Waiting for {time_to_wait:.0f} seconds.")

            # Wait for the scheduled time, but check stop event periodically
            # This allows the thread to be stopped gracefully
            while time_to_wait > 0 and not self._stop_event.is_set():
                wait_chunk = min(time_to_wait, 60) # Check every minute
                if not(self.saxo_client._is_authenticated()):
                    logger.error("SaxoClient is not authenticated.")
                logger.debug(f"Waiting for {wait_chunk} seconds...")
                self._stop_event.wait(wait_chunk)
                time_to_wait -= wait_chunk

            if not self._stop_event.is_set():
                logger.info("Scheduled time reached. Placing order...")
                self._place_order()
                # After placing the order, the next iteration of the loop will naturally
                # calculate the next scheduled time using cronsim, ensuring it's in the future.
            else:
                logger.info("Order scheduler stopping.")

    def start_scheduler_thread(self):
        if self._scheduler_thread is None or not self._scheduler_thread.is_alive():
            logger.info(f"Starting order scheduler thread with cron expression: {self.cron_expression}.")
            self._stop_event.clear()
            self._scheduler_thread = threading.Thread(target=self._schedule_loop, daemon=True)
            self._scheduler_thread.start()
        else:
            logger.info("Order scheduler thread is already running.")

    def stop_scheduler_thread(self):
        if self._scheduler_thread and self._scheduler_thread.is_alive():
            logger.info("Stopping order scheduler thread.")
            self._stop_event.set()
            self._scheduler_thread.join()
