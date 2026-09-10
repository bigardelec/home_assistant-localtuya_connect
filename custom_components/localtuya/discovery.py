"""Discovery module for Tuya devices.

Entirely based on tuya-convert.py from tuya-convert:

https://github.com/ct-Open-Source/tuya-convert/blob/master/scripts/tuya-discovery.py
"""
import asyncio
import json
import logging
import socket
from hashlib import md5

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .pytuya import (
    unpack_message,
    pack_message,
    TuyaMessage,
    PREFIX_BIN,
    PREFIX_6699_BIN,
    PREFIX_6699_VALUE,
    REQ_DEVINFO,
)

_LOGGER = logging.getLogger(__name__)

UDP_KEY = md5(b"yGAdlopoPVldABfn").digest()
UDP_COMMAND = b"\x00\x00\x00\x00"

DEFAULT_TIMEOUT = 6.0
V35_DISCOVERY_PORT = 7000
V35_DISCOVERY_INTERVAL = 6.0


def _decrypt_legacy(payload):
    """Decrypt old-style (pre-3.5) AES-ECB broadcast payload."""

    def _unpad(data):
        return data[: -ord(data[len(data) - 1 :])]

    cipher = Cipher(algorithms.AES(UDP_KEY), modes.ECB(), default_backend())
    decryptor = cipher.decryptor()
    return _unpad(decryptor.update(payload) + decryptor.finalize()).decode()


def decrypt_udp(message):
    """Decrypt encrypted UDP broadcasts (supports legacy and 3.5/6699 format)."""
    if message[:4] == PREFIX_BIN:
        payload = message[20:-8]
        if message[8:12] == UDP_COMMAND:
            return payload.decode()
        return _decrypt_legacy(payload)

    if message[:4] == PREFIX_6699_BIN:
        unpacked = unpack_message(
            message, hmac_key=UDP_KEY, no_retcode=None, logger=_LOGGER
        )
        payload = unpacked.payload.decode()
        # some apps pad with trailing null bytes
        while payload and payload[-1] == chr(0):
            payload = payload[:-1]
        return payload

    # fallback: try legacy decrypt on raw message
    return _decrypt_legacy(message)


class TuyaDiscovery(asyncio.DatagramProtocol):
    """Datagram handler listening for Tuya broadcast messages."""

    def __init__(self, callback=None):
        """Initialize a new BaseDiscovery."""
        self.devices = {}
        self._listeners = []
        self._callback = callback
        self._v35_transport = None
        self._v35_broadcast_task = None

    async def start(self):
        """Start discovery by listening to broadcasts."""
        loop = asyncio.get_running_loop()
        listener = loop.create_datagram_endpoint(
            lambda: self, local_addr=("0.0.0.0", 6666), reuse_port=True
        )
        encrypted_listener = loop.create_datagram_endpoint(
            lambda: self, local_addr=("0.0.0.0", 6667), reuse_port=True
        )
        v35_listener = loop.create_datagram_endpoint(
            lambda: self,
            local_addr=("0.0.0.0", V35_DISCOVERY_PORT),
            reuse_port=True,
            allow_broadcast=True,
        )

        self._listeners = await asyncio.gather(
            listener, encrypted_listener, v35_listener
        )
        self._v35_transport = self._listeners[2][0]
        self._v35_broadcast_task = loop.create_task(self._v35_broadcast_loop())
        _LOGGER.debug(
            "Listening to broadcasts on UDP ports 6666, 6667 and 7000"
        )

    def close(self):
        """Stop discovery."""
        self._callback = None

        if self._v35_broadcast_task is not None:
            self._v35_broadcast_task.cancel()
            self._v35_broadcast_task = None

        for transport, _ in self._listeners:
            transport.close()

        self._listeners = []
        self._v35_transport = None

    @staticmethod
    def _get_local_ip():
        """Return the IPv4 address used to reach the local network."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # No packet is sent by UDP connect(); this only asks the OS which
            # source address it would use for a normal routed connection.
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
        except OSError:
            try:
                return socket.gethostbyname(socket.gethostname())
            except OSError:
                return None
        finally:
            sock.close()

    def _send_v35_discovery_request(self):
        """Solicit discovery replies from Tuya 3.5 devices on UDP/7000."""
        if self._v35_transport is None:
            return

        local_ip = self._get_local_ip()
        if not local_ip or local_ip.startswith("127."):
            _LOGGER.debug(
                "Unable to determine a usable local IPv4 address for Tuya 3.5 discovery"
            )
            return

        payload = json.dumps(
            {"from": "app", "ip": local_ip}, separators=(",", ":")
        ).encode()
        message = TuyaMessage(
            0, REQ_DEVINFO, None, payload, 0, True, PREFIX_6699_VALUE, True
        )
        packet = pack_message(message, hmac_key=UDP_KEY)

        try:
            self._v35_transport.sendto(
                packet, ("255.255.255.255", V35_DISCOVERY_PORT)
            )
            _LOGGER.debug(
                "Sent Tuya 3.5 discovery request from %s to UDP/7000", local_ip
            )
        except OSError as ex:
            _LOGGER.debug("Failed to send Tuya 3.5 discovery request: %s", ex)

    async def _v35_broadcast_loop(self):
        """Periodically solicit silent Tuya 3.5 devices."""
        try:
            while True:
                self._send_v35_discovery_request()
                await asyncio.sleep(V35_DISCOVERY_INTERVAL)
        except asyncio.CancelledError:
            return

    def datagram_received(self, data, addr):
        """Handle received broadcast message."""
        try:
            try:
                decoded_str = decrypt_udp(data)
            except Exception:  # pylint: disable=broad-except
                decoded_str = data.decode()
            decoded = json.loads(decoded_str)

            # The host can receive its own UDP/7000 solicitation packet.
            # It is not a device announcement and has no gwId.
            if not isinstance(decoded, dict) or not decoded.get("gwId"):
                _LOGGER.debug("Ignoring non-device Tuya broadcast: %s", decoded)
                return

            self.device_found(decoded)
        except Exception as ex:  # pylint: disable=broad-except
            _LOGGER.debug(
                "Failed to decode broadcast from %r: %r [%s]", addr[0], data, ex
            )

    def device_found(self, device):
        """Discover a new device."""
        if device.get("gwId") not in self.devices:
            self.devices[device.get("gwId")] = device
            _LOGGER.debug("Discovered device: %s", device)

        if self._callback:
            self._callback(device)


async def discover():
    """Discover and return devices on local network."""
    discovery = TuyaDiscovery()
    try:
        await discovery.start()
        await asyncio.sleep(DEFAULT_TIMEOUT)
    finally:
        discovery.close()
    return discovery.devices