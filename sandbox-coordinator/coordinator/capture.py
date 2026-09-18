"""Network capture.

The sandbox bridge has no gateway, so nothing a sample sends is ever
answered -- but the attempt itself is the evidence. tcpdump on the clone's
tap records every DNS question, TCP SYN and cleartext HTTP request.
"""

from __future__ import annotations

import subprocess
import time


class Capture:
    def __init__(self, iface: str, pcap_path: str) -> None:
        self.iface = iface
        self.pcap_path = pcap_path
        self._proc: subprocess.Popen | None = None

    def start(self) -> bool:
        try:
            self._proc = subprocess.Popen(
                ["tcpdump", "-i", self.iface, "-s", "0", "-U", "-w", self.pcap_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            return False
        time.sleep(1.0)
        return self._proc.poll() is None

    def stop(self) -> None:
        if self._proc is None:
            return
        self._proc.terminate()
        try:
            self._proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self._proc.kill()
