# stress_test.py
"""
Manual stress testing script.
Spawns N agent simulators, tracks metrics.
"""

import requests
import threading
import time
import json
import uuid
from pathlib import Path
import random
from datetime import datetime
from cryptography.fernet import Fernet
import psutil
import matplotlib.pyplot as plt
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configuration
TARGET_URL = "https://127.0.0.1"
NUM_AGENTS = 50
BEACON_INTERVAL = 5  # seconds
DURATION = 10  # 5 minutes
FERNET_KEY = "8zQ0wY9DwMZ5N63DR-3h9C7F5htGvA2I7ReG0i8ER6U="
cipher = Fernet(FERNET_KEY)
session = requests.Session()
BASE_DIR = Path(__file__).resolve().parent
CA_CERT = BASE_DIR / "keys" / "ca.crt"

# Session configuration
session.verify = str(CA_CERT)
session.cert = (
    BASE_DIR / "keys" / "agent1.crt",
    BASE_DIR / "keys" / "agent1.key",
)


class MetricsCollector:
    """Track server metrics during test."""

    def __init__(self):
        self.timestamps = []
        self.cpu_usage = []
        self.memory_usage = []
        self.beacon_times = []
        self.result_times = []
        self.errors = 0
        self.success = 0
        self.lock = threading.Lock()

    def record_beacon(self, response_time):
        with self.lock:
            self.beacon_times.append(response_time)
            self.success += 1

    def record_error(self):
        with self.lock:
            self.errors += 1

    def collect_system_metrics(self):
        """Collect CPU/memory every second."""
        while True:
            try:
                cpu = psutil.cpu_percent(interval=1)
                memory = psutil.virtual_memory().percent

                with self.lock:
                    self.timestamps.append(datetime.now())
                    self.cpu_usage.append(cpu)
                    self.memory_usage.append(memory)
            except:
                pass

            time.sleep(1)

    def print_report(self):
        """Print test results."""
        print("\n" + "=" * 70)
        print("STRESS TEST REPORT")
        print("=" * 70)

        print(f"\nAgents Simulated: {NUM_AGENTS}")
        print(f"Test Duration: {DURATION}s")
        print(f"\nRequests:")
        print(f"  Successful: {self.success}")
        print(f"  Failed: {self.errors}")
        print(f"  Total: {self.success + self.errors}")

        if self.beacon_times:
            times = self.beacon_times
            print(f"\nBeacon Response Times:")
            print(f"  Min: {min(times):.3f}s")
            print(f"  Max: {max(times):.3f}s")
            print(f"  Avg: {sum(times) / len(times):.3f}s")
            print(f"  P95: {sorted(times)[int(len(times) * 0.95)]:.3f}s")
            print(f"  P99: {sorted(times)[int(len(times) * 0.99)]:.3f}s")

        if self.cpu_usage:
            print(f"\nCPU Usage:")
            print(f"  Min: {min(self.cpu_usage):.1f}%")
            print(f"  Max: {max(self.cpu_usage):.1f}%")
            print(f"  Avg: {sum(self.cpu_usage) / len(self.cpu_usage):.1f}%")

        if self.memory_usage:
            print(f"\nMemory Usage:")
            print(f"  Min: {min(self.memory_usage):.1f}%")
            print(f"  Max: {max(self.memory_usage):.1f}%")
            print(f"  Avg: {sum(self.memory_usage) / len(self.memory_usage):.1f}%")

        print("\n" + "=" * 70)

    def plot_results(self):
        """Generate graphs."""
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(12, 8))

        # CPU usage
        ax1.plot(self.timestamps, self.cpu_usage)
        ax1.set_title("CPU Usage Over Time")
        ax1.set_ylabel("CPU %")

        # Memory usage
        ax2.plot(self.timestamps, self.memory_usage)
        ax2.set_title("Memory Usage Over Time")
        ax2.set_ylabel("Memory %")

        # Response times
        ax3.plot(range(len(self.beacon_times)), self.beacon_times)
        ax3.set_title("Beacon Response Times")
        ax3.set_ylabel("Response Time (s)")

        # Success vs Errors
        ax4.bar(['Success', 'Errors'], [self.success, self.errors])
        ax4.set_title("Request Results")
        ax4.set_ylabel("Count")

        plt.tight_layout()
        plt.savefig('stress_test_results.png')
        print("\nGraph saved to stress_test_results.png")


class SimulatedAgent(threading.Thread):
    """Simulate a single agent."""

    def __init__(self, agent_id, metrics):
        super().__init__(daemon=True)
        self.agent_id = agent_id
        self.metrics = metrics
        self.token = None
        self.running = True

        # Give each agent its own isolated session
        self.agent_session = requests.Session()
        self.agent_session.verify = str(CA_CERT)
        self.agent_session.cert = (
            BASE_DIR / "keys" / "agent1.crt",
            BASE_DIR / "keys" / "agent1.key",
        )

    def login(self):
        """Get auth token."""
        try:
            numeric_id = int(self.agent_id.split('-')[-1])
            payload = {
                "username": "agent2",
                "password": "pass2",
                "agent_id": numeric_id,
                "hostname": f"host-{random.randint(1, 100)}",
                "user": "root",
                "os": "Linux"
            }

            # Use the agent-specific session
            response = self.agent_session.post(
                f"{TARGET_URL}/login",
                json=payload,
                verify=False,
                timeout=5
            )

            if response.status_code == 200:
                self.token = response.json().get('token')
                return True
            else:
                print(f"[{self.agent_id}] Login failed: HTTP status {response.status_code}")
                return False
        except Exception as e:
            print(f"[{self.agent_id}] Login exception occurred: {e}")
            return False

    def beacon(self):
        """Send beacon."""
        try:
            beacon_data = {
                "id": self.agent_id,
                "hostname": f"host-{random.randint(1, 100)}",
                "user": "root",
                "os": "Linux",
                "ip": f"192.168.1.{random.randint(1, 254)}"
            }

            encrypted = cipher.encrypt(
                json.dumps(beacon_data).encode()
            ).decode()

            start = time.time()
            # Use the agent-specific session
            response = self.agent_session.post(
                f"{TARGET_URL}/beacon",
                json={"data": encrypted},
                headers={"TOKEN": str(self.token)},
                verify=False,
                timeout=10
            )
            elapsed = time.time() - start

            if response.status_code == 200:
                self.metrics.record_beacon(elapsed)
            else:
                self.metrics.record_error()

        except Exception as e:
            self.metrics.record_error()

    def run(self):
        """Main loop."""
        # Execute login inside the thread to avoid blocking sequential startup
        if not self.login():
            print(f"[{self.agent_id}] Skipping run loop due to initialization failure.")
            return

        start_time = time.time()
        while self.running and (time.time() - start_time) < DURATION:
            self.beacon()
            time.sleep(BEACON_INTERVAL + random.uniform(-1, 1))


def run_stress_test():
    """Main stress test."""
    print(f"Starting stress test: {NUM_AGENTS} agents, {DURATION}s duration")

    metrics = MetricsCollector()

    # Start system metrics collector
    metrics_thread = threading.Thread(
        target=metrics.collect_system_metrics,
        daemon=True
    )
    metrics_thread.start()

    # Create and immediately start agents asynchronously
    agents = []
    for i in range(NUM_AGENTS):
        agent = SimulatedAgent(f"test-agent-{i}", metrics)
        agent.start()
        agents.append(agent)
        time.sleep(0.1)  # Stagger thread creation slightly

    # Wait for test duration
    time.sleep(DURATION)

    # Stop agents
    for agent in agents:
        agent.running = False

    # Print results
    metrics.print_report()
    metrics.plot_results()


if __name__ == "__main__":
    run_stress_test()