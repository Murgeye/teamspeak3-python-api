"""
This module provides a socket wrapper for a TeamSpeak 3 connection.
"""
import socket

from .utilities import TS3ConnectionClosedException

class SocketWrapper:
    """
    Socket wrapper for TS3 connections. Provides some helper functions.
    """
    # pylint: disable=too-many-arguments
    def __init__(self, host, port, timeout=10, timeout_limit=3):
        """
        Create a new socket wrapper.
        :param host: Hostname of the Server  to connect to.
        :param port: Ts3Server port.
        :param timeout: Timeout in seconds (default=10)
        :param timeout_limit: How often a timeout is allowed to happen while reading before we
                              assume the server connection died. (default=3)
        """
        self._buffer = b""
        self._conn = socket.create_connection((host, port), timeout=timeout)
        self.timeout = timeout
        self.timeout_limit = timeout_limit

    def read_until(self, delimiter, timeout=None):
        """
        Read until a given byte string, delimiter, or until  the timeout limit set is reached.
        The timeout parameter is ignored.
        """
        timeout_cnt = 0
        if timeout is not None:
            self._conn.settimeout(timeout)
        while True:
            delimiter_pos = self._buffer.find(delimiter)
            if delimiter_pos == -1:
                try:
                    received = self._conn.recv(4096)
                    timeout_cnt = 0
                except socket.timeout as exc:
                    timeout_cnt += 1
                    if timeout_cnt >= self.timeout_limit:
                        raise TS3ConnectionClosedException("Socket connection timeout\
                                                           limit received!") from exc
                    continue
                if len(received) == 0:
                    raise TS3ConnectionClosedException("Socket connection was closed!")
                self._buffer += received
            else:
                break
        data = self._buffer[:delimiter_pos + len(delimiter)]
        self._buffer = self._buffer[delimiter_pos + len(delimiter):]
        if timeout is not None:
            self._conn.settimeout(self.timeout)
        return data

    def write(self, data):
        """
        Write bytes in data to the connection.
        """
        try:
            self._conn.send(data)
        except OSError as exc:
            raise TS3ConnectionClosedException(OSError) from exc

    def close(self):
        """"
        Close the underlying connection.
        """
        self._conn.close()
