import threading
import time
import logging
from datetime import datetime, timedelta

# Assuming saxo_sdk is accessible in the Python path
from saxo_sdk.client import SaxoClient
from .config import config

logger = logging.getLogger()


class OrderScheduler:
    def __init__(self, token_manager: TokenManager):
        self.token_manager = token_manager
        self.saxo_client = token_manager.saxo_client # Access SaxoClient from TokenManager
        self.order_schedule_time_str = config.ORDER_SCHEDULE_TIME
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
            now = datetime.now()
            schedule_time = datetime.strptime(self.order_schedule_time_str, "%H:%M").replace(
                year=now.year, month=now.month, day=now.day
            )

            if now > schedule_time:
                # If the scheduled time for today has passed, schedule for tomorrow
                schedule_time += timedelta(days=1)

            time_to_wait = (schedule_time - now).total_seconds()
            logger.info(f"Next order scheduled for: {schedule_time.strftime('%Y-%m-%d %H:%M:%S')}. Waiting for {time_to_wait:.0f} seconds.")

            # Wait for the scheduled time, but check stop event periodically
            # This allows the thread to be stopped gracefully
            while time_to_wait > 0 and not self._stop_event.is_set():
                wait_chunk = min(time_to_wait, 60) # Check every minute
                self._stop_event.wait(wait_chunk)
                time_to_wait -= wait_chunk

            if not self._stop_event.is_set():
                logger.info("Scheduled time reached. Placing order...")
                self._place_order()
                # After placing the order, schedule for the next day
                # This loop will naturally re-calculate for the next day
                # To avoid placing multiple orders in the same minute,
                # we can add a small delay or ensure the schedule_time calculation
                # correctly moves to the next day immediately after execution.
                # The current logic will naturally move to the next day in the next iteration.
            else:
                logger.info("Order scheduler stopping.")

    def start_scheduler_thread(self):
        if self._scheduler_thread is None or not self._scheduler_thread.is_alive():
            logger.info(f"Starting order scheduler thread for {self.order_schedule_time_str}.")
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
