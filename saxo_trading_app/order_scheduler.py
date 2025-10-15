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
        self.saxo_client = client
        self.orders = config.ORDERS
        self._scheduler_thread = None
        self._stop_event = threading.Event()
        self.next_schedule_times = {} # To store next schedule time for each order

    def _place_order(self, order_name, order_details):
        # Create a mutable copy of order_details to remove internal fields
        order_payload = order_details.copy()
        # Remove ORDER_SCHEDULE_TIME as it's an internal scheduler field, not for the bank API
        if "ORDER_SCHEDULE_TIME" in order_payload:
            del order_payload["ORDER_SCHEDULE_TIME"]

        logger.info(f"Attempting to place order '{order_name}': {order_payload}")
        try:
            order_response = self.saxo_client.place_order(order_payload)
            logger.info(f"Order '{order_name}' placed successfully: {order_response}")
        except Exception as e:
            logger.error(f"Failed to place order '{order_name}': {e}")

    def _schedule_loop(self):
        while not self._stop_event.is_set():
            now = datetime.now()
            now_truncated = now.replace(microsecond=0) # Normalize 'now' to seconds for cron calculations and comparisons
            min_time_to_wait = float('inf')
            orders_to_execute = []

            for order_name, order_details in self.orders.items():
                cron_expression = order_details.get("ORDER_SCHEDULE_TIME")
                if not cron_expression:
                    logger.warning(f"Order '{order_name}' has no 'ORDER_SCHEDULE_TIME'. Skipping.")
                    continue

                # Calculate next schedule time if not already calculated or if it's in the past
                # Only recalculate if the stored schedule time is strictly in the past (compared to now_truncated),
                # or if it's the first time calculating for this order.
                if order_name not in self.next_schedule_times or self.next_schedule_times[order_name] < now_truncated:
                    logger.debug(f"Recalculating schedule for '{order_name}'. Current stored: {self.next_schedule_times.get(order_name, 'None')}, Now: {now_truncated.strftime('%Y-%m-%d %H:%M:%S')}")
                    try:
                        cron = CronSim(expr=cron_expression, dt=now_truncated) # Use now_truncated for CronSim
                        self.next_schedule_times[order_name] = next(cron)
                        logger.debug(f"Calculated next schedule for '{order_name}': {self.next_schedule_times[order_name].strftime('%Y-%m-%d %H:%M:%S')}")
                    except Exception as e:
                        logger.error(f"Error calculating cron for order '{order_name}': {e}")
                        continue
                else:
                    logger.debug(f"Using existing schedule for '{order_name}': {self.next_schedule_times[order_name].strftime('%Y-%m-%d %H:%M:%S')}")


                schedule_time = self.next_schedule_times[order_name]
                # Compare with the full 'now' for execution, as schedule_time is already truncated by CronSim
                time_until_schedule = (schedule_time - now).total_seconds()
                logger.debug(f"Order '{order_name}': schedule_time={schedule_time.strftime('%Y-%m-%d %H:%M:%S')}, now={now.strftime('%Y-%m-%d %H:%M:%S')}, time_until_schedule={time_until_schedule:.2f}")

                if now >= schedule_time: # This condition should now correctly trigger when the time arrives
                    logger.debug(f"Order '{order_name}' is due. Adding to execution list.")
                    orders_to_execute.append((order_name, order_details))
                else:
                    logger.debug(f"Order '{order_name}' not yet due. Time until schedule: {time_until_schedule:.0f} seconds.")
                    min_time_to_wait = min(min_time_to_wait, time_until_schedule)

            logger.debug(f"Finished iterating orders. Orders to execute: {len(orders_to_execute)}")
            if orders_to_execute:
                if not self.saxo_client._is_authenticated():
                    logger.error("SaxoClient is not authenticated. Cannot place orders.")
                else:
                    logger.debug(f"Processing {len(orders_to_execute)} orders for execution.")
                    for order_name, order_details in orders_to_execute:
                        logger.debug(f"Attempting to place order '{order_name}'.")
                        self._place_order(order_name, order_details)
                        # Recalculate next schedule time immediately after execution
                        cron_expression = order_details.get("ORDER_SCHEDULE_TIME")
                        if cron_expression:
                            try:
                                # Use the *executed* schedule_time as the base for finding the next one, truncated
                                cron = CronSim(expr=cron_expression, dt=schedule_time.replace(microsecond=0))
                                next_future_schedule = next(cron)
                                # Ensure it's strictly in the future relative to the *current* now_truncated
                                while next_future_schedule <= now_truncated:
                                    next_future_schedule = next(cron)
                                self.next_schedule_times[order_name] = next_future_schedule
                                logger.debug(f"Recalculated next schedule for '{order_name}' after execution: {self.next_schedule_times[order_name].strftime('%Y-%m-%d %H:%M:%S')}")
                            except Exception as e:
                                logger.error(f"Error recalculating cron for order '{order_name}' after execution: {e}")
                                del self.next_schedule_times[order_name]
                # After executing orders, immediately re-evaluate for the next loop iteration
                # This avoids waiting if another order is immediately due or if cron recalculation was slow
                continue

            if min_time_to_wait == float('inf'):
                logger.info("No orders with valid schedule times found. Waiting indefinitely.")
                self._stop_event.wait() # Wait until stopped
            else:
                logger.info(f"Next order(s) scheduled in {min_time_to_wait:.0f} seconds. Waiting...")
                self._stop_event.wait(min(min_time_to_wait, 60)) # Check every minute or sooner if min_time_to_wait is small

        logger.info("Order scheduler stopping.")

    def start_scheduler_thread(self):
        if not self.orders:
            logger.warning("No orders configured in params.json. Scheduler will not start.")
            return

        if self._scheduler_thread is None or not self._scheduler_thread.is_alive():
            logger.info("Starting order scheduler thread for multiple orders.")
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
